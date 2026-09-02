"""
Device management + enrollment endpoints.

Human-facing (require a user token):
  POST /devices             -> register a new device, returns a one-time enroll token
  GET  /devices             -> list devices (super: all; owner: only their own)
  GET  /devices/{id}        -> one device's details

Phone-facing (no user token; uses the one-time enroll token):
  POST /devices/enroll      -> phone exchanges enroll token for a long-lived device token
"""
import secrets

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from ..deps import (
    CurrentUser,
    SessionDep,
    owner_can_access_device,
)
from ..models import Device, DeviceStatus, Role, User, utcnow
from ..schemas import (
    CreateDeviceRequest,
    CreateDeviceResponse,
    DeviceResponse,
    EnrollRequest,
    EnrollResponse,
)
from ..security import create_device_token

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("", response_model=CreateDeviceResponse, status_code=201)
def create_device(body: CreateDeviceRequest, user: CurrentUser, session: SessionDep):
    # Decide who will own this device.
    if user.role == Role.super_admin:
        # Super admin may target any owner; defaults to themselves if omitted.
        owner_id = body.owner_id or user.id
        if body.owner_id and not session.get(User, body.owner_id):
            raise HTTPException(status_code=404, detail="Target owner not found")
    else:
        # Owners can only create devices for themselves.
        if body.owner_id and body.owner_id != user.id:
            raise HTTPException(status_code=403, detail="Cannot create devices for others")
        owner_id = user.id

    device = Device(
        owner_id=owner_id,
        name=body.name,
        platform=body.platform,
        model=body.model,
        imei=body.imei,
        status=DeviceStatus.pending,
        enroll_token=secrets.token_urlsafe(24),   # one-time secret for the phone
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


@router.get("", response_model=list[DeviceResponse])
def list_devices(user: CurrentUser, session: SessionDep):
    query = select(Device)
    if user.role != Role.super_admin:
        query = query.where(Device.owner_id == user.id)
    devices = session.exec(query).all()

    # For super admins, attach each device's owner email so the fleet view can
    # show whose phone it is. (Owners already know — it's theirs.)
    if user.role == Role.super_admin:
        owners = {u.id: u.email for u in session.exec(select(User)).all()}
        result = []
        for d in devices:
            data = DeviceResponse.model_validate(d, from_attributes=True)
            data.owner_email = owners.get(d.owner_id)
            result.append(data)
        return result
    return devices


@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(device_id: int, user: CurrentUser, session: SessionDep):
    device = session.get(Device, device_id)
    if not device or not owner_can_access_device(user, device):
        # Hide existence from users who shouldn't see it.
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.post("/enroll", response_model=EnrollResponse)
def enroll(body: EnrollRequest, session: SessionDep):
    """Called by the phone itself, using the one-time enroll token."""
    device = session.exec(
        select(Device).where(Device.enroll_token == body.enroll_token)
    ).first()
    if not device:
        raise HTTPException(status_code=400, detail="Invalid enroll token")
    if device.enrolled_at is not None:
        raise HTTPException(status_code=409, detail="Device already enrolled")

    # Fill in details the phone reports, and consume the one-time token.
    if body.model:
        device.model = body.model
    if body.imei:
        device.imei = body.imei
    device.status = DeviceStatus.active
    device.enrolled_at = utcnow()
    device.last_seen = utcnow()
    device.enroll_token = None       # token is single-use

    session.add(device)
    session.commit()
    session.refresh(device)

    token = create_device_token(device_id=device.id, token_version=device.token_version)
    return EnrollResponse(device_id=device.id, device_token=token)
