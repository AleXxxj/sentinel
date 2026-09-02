"""
Command channel — owner-issued actions a phone carries out.

This is how the "unique process only the owner controls" works: the agent on the
phone NEVER removes itself on its own. It only acts when it polls the server and
finds a command that an authenticated owner (or super admin) issued. When it
finishes a `remove`, we mark the device removed and bump its token_version,
which instantly revokes the device's token.

Human-facing (user token):
  POST /devices/{id}/commands        -> issue a command (ring/lock/wipe/remove)
  GET  /devices/{id}/commands        -> command history

Phone-facing (device token):
  GET  /device/commands              -> pending commands for THIS phone
  POST /device/commands/{id}/result  -> report a command's outcome
"""
from fastapi import APIRouter, HTTPException
from sqlmodel import desc, select

from ..deps import CurrentDevice, CurrentUser, SessionDep, owner_can_access_device
from ..models import Command, CommandStatus, CommandType, Device, DeviceStatus, utcnow
from ..schemas import CommandCreate, CommandResponse, CommandResultIn

router = APIRouter(tags=["commands"])


def _get_owned_device(device_id: int, user, session) -> Device:
    device = session.get(Device, device_id)
    if not device or not owner_can_access_device(user, device):
        raise HTTPException(status_code=404, detail="Device not found")
    return device


# --- Human side ---

@router.post("/devices/{device_id}/commands", response_model=CommandResponse, status_code=201)
def issue_command(device_id: int, body: CommandCreate, user: CurrentUser, session: SessionDep):
    device = _get_owned_device(device_id, user, session)

    # Don't queue duplicate pending commands of the same type.
    existing = session.exec(
        select(Command).where(
            Command.device_id == device_id,
            Command.type == body.type,
            Command.status == CommandStatus.pending,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A '{body.type.value}' command is already pending")

    cmd = Command(device_id=device_id, type=body.type, issued_by=user.id)
    session.add(cmd)
    session.commit()
    session.refresh(cmd)
    return cmd


@router.get("/devices/{device_id}/commands", response_model=list[CommandResponse])
def command_history(device_id: int, user: CurrentUser, session: SessionDep):
    _get_owned_device(device_id, user, session)
    return session.exec(
        select(Command).where(Command.device_id == device_id).order_by(desc(Command.created_at))
    ).all()


# --- Phone side ---

@router.get("/device/commands", response_model=list[CommandResponse])
def poll_commands(device: CurrentDevice, session: SessionDep):
    """The phone asks: is there anything for me to do?"""
    device.last_seen = utcnow()
    session.add(device)
    cmds = session.exec(
        select(Command).where(
            Command.device_id == device.id,
            Command.status == CommandStatus.pending,
        )
    ).all()
    session.commit()
    return cmds


@router.post("/device/commands/{command_id}/result", response_model=CommandResponse)
def report_result(
    command_id: int, body: CommandResultIn, device: CurrentDevice, session: SessionDep
):
    cmd = session.get(Command, command_id)
    if not cmd or cmd.device_id != device.id:
        raise HTTPException(status_code=404, detail="Command not found")

    cmd.status = body.status
    cmd.result = body.result
    if body.status in (CommandStatus.completed, CommandStatus.failed):
        cmd.completed_at = utcnow()
    session.add(cmd)

    # A completed `remove` retires the device and revokes its token by bumping
    # the version, so no previously-issued device token works any more.
    if cmd.type == CommandType.remove and body.status == CommandStatus.completed:
        device.status = DeviceStatus.removed
        device.token_version += 1
        session.add(device)

    session.commit()
    session.refresh(cmd)
    return cmd
