"""
Location beacon endpoints.

Phone-facing (device token):
  POST /beacons                    -> phone submits a location fix

Human-facing (user token):
  GET  /devices/{id}/latest        -> most recent location of a device
  GET  /devices/{id}/beacons       -> location history (newest first)
"""
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import desc, select

from ..deps import CurrentDevice, CurrentUser, SessionDep, owner_can_access_device
from ..models import Beacon, Device, utcnow
from ..schemas import BeaconIn, BeaconResponse

# Two routers: one under /beacons for the phone, one under /devices for humans.
router = APIRouter(tags=["beacons"])


@router.post("/beacons", response_model=BeaconResponse, status_code=201)
def submit_beacon(body: BeaconIn, device: CurrentDevice, session: SessionDep):
    """The enrolled phone reports where it is."""
    beacon = Beacon(
        device_id=device.id,
        latitude=body.latitude,
        longitude=body.longitude,
        accuracy_m=body.accuracy_m,
        battery_pct=body.battery_pct,
        is_charging=body.is_charging,
        recorded_at=body.recorded_at or utcnow(),
        received_at=utcnow(),
    )
    session.add(beacon)

    # Keep the device's "last seen" fresh so the dashboard can show liveness.
    device.last_seen = utcnow()
    session.add(device)

    session.commit()
    session.refresh(beacon)
    return beacon


def _get_owned_device(device_id: int, user, session) -> Device:
    device = session.get(Device, device_id)
    if not device or not owner_can_access_device(user, device):
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get("/devices/{device_id}/latest", response_model=BeaconResponse)
def latest_beacon(device_id: int, user: CurrentUser, session: SessionDep):
    _get_owned_device(device_id, user, session)
    beacon = session.exec(
        select(Beacon)
        .where(Beacon.device_id == device_id)
        .order_by(desc(Beacon.recorded_at))
    ).first()
    if not beacon:
        raise HTTPException(status_code=404, detail="No beacons yet for this device")
    return beacon


@router.get("/devices/{device_id}/beacons", response_model=list[BeaconResponse])
def beacon_history(
    device_id: int,
    user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=100, le=1000),
):
    _get_owned_device(device_id, user, session)
    return session.exec(
        select(Beacon)
        .where(Beacon.device_id == device_id)
        .order_by(desc(Beacon.recorded_at))
        .limit(limit)
    ).all()
