"""
Alert endpoints — the backbone of the theft features.

Phone-facing (device token):
  POST /alerts                       -> phone raises an alert (SIM swap, failed
                                        unlock, powering off, low battery)

Human-facing (user token):
  GET  /devices/{id}/alerts          -> list a device's alerts (newest first)
  POST /alerts/{alert_id}/ack        -> mark an alert as seen
  POST /devices/{id}/lost            -> owner flags the device as lost/stolen
"""
import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import desc, select

from ..config import settings
from ..deps import CurrentDevice, CurrentUser, SessionDep, owner_can_access_device
from ..models import Alert, AlertType, Device, DeviceStatus, utcnow
from ..schemas import AlertIn, AlertResponse

router = APIRouter(tags=["alerts"])

# Accepted image types and their file extensions, checked by magic bytes so a
# phone can't upload a disguised non-image.
_IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": ".jpg",              # JPEG
    b"\x89PNG\r\n\x1a\n": ".png",         # PNG
}


def _detect_image_ext(data: bytes):
    for sig, ext in _IMAGE_SIGNATURES.items():
        if data.startswith(sig):
            return ext
    return None


def _evidence_path(alert_id: int, ext: str) -> str:
    os.makedirs(settings.EVIDENCE_DIR, exist_ok=True)
    return os.path.join(settings.EVIDENCE_DIR, f"alert_{alert_id}{ext}")


@router.post("/alerts", response_model=AlertResponse, status_code=201)
def raise_alert(body: AlertIn, device: CurrentDevice, session: SessionDep):
    """The enrolled phone reports a notable event."""
    alert = Alert(
        device_id=device.id,
        type=body.type,
        message=body.message,
        latitude=body.latitude,
        longitude=body.longitude,
        new_sim_number=body.new_sim_number,
        photo_url=body.photo_url,
    )
    session.add(alert)

    # A SIM swap on a device the owner already flagged lost is a strong signal;
    # keep the device marked lost and just record the alert. Any alert also
    # refreshes "last seen".
    device.last_seen = utcnow()
    session.add(device)

    session.commit()
    session.refresh(alert)
    return alert


def _get_owned_device(device_id: int, user, session) -> Device:
    device = session.get(Device, device_id)
    if not device or not owner_can_access_device(user, device):
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get("/devices/{device_id}/alerts", response_model=list[AlertResponse])
def list_alerts(device_id: int, user: CurrentUser, session: SessionDep):
    _get_owned_device(device_id, user, session)
    return session.exec(
        select(Alert).where(Alert.device_id == device_id).order_by(desc(Alert.created_at))
    ).all()


@router.post("/alerts/{alert_id}/ack", response_model=AlertResponse)
def acknowledge_alert(alert_id: int, user: CurrentUser, session: SessionDep):
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    # Make sure the user is allowed to see this alert's device.
    _get_owned_device(alert.device_id, user, session)

    alert.acknowledged = True
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


@router.post("/device/alerts/{alert_id}/photo", response_model=AlertResponse)
async def upload_evidence(
    alert_id: int, device: CurrentDevice, session: SessionDep, file: UploadFile = File(...)
):
    """The phone uploads an evidence photo (e.g. a failed-unlock camera shot)."""
    alert = session.get(Alert, alert_id)
    if not alert or alert.device_id != device.id:
        raise HTTPException(status_code=404, detail="Alert not found")

    data = await file.read()
    if len(data) > settings.MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo too large")
    ext = _detect_image_ext(data)
    if not ext:
        raise HTTPException(status_code=400, detail="File is not a JPEG or PNG image")

    path = _evidence_path(alert_id, ext)
    with open(path, "wb") as f:
        f.write(data)

    # photo_url points at the authenticated retrieval endpoint, not a public file.
    alert.photo_url = f"/alerts/{alert_id}/photo"
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


@router.get("/alerts/{alert_id}/photo")
def get_evidence(alert_id: int, user: CurrentUser, session: SessionDep):
    """Owner/super downloads the evidence photo (access-controlled)."""
    alert = session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    _get_owned_device(alert.device_id, user, session)   # enforce ownership

    for ext in (".jpg", ".png"):
        path = _evidence_path(alert_id, ext)
        if os.path.exists(path):
            return FileResponse(path, media_type="image/jpeg" if ext == ".jpg" else "image/png")
    raise HTTPException(status_code=404, detail="No photo for this alert")


@router.post("/devices/{device_id}/lost", response_model=AlertResponse, status_code=201)
def mark_lost(device_id: int, user: CurrentUser, session: SessionDep):
    """Owner flags a device as lost/stolen. Sets status and logs an alert."""
    device = _get_owned_device(device_id, user, session)
    device.status = DeviceStatus.lost
    session.add(device)

    alert = Alert(
        device_id=device.id,
        type=AlertType.marked_lost,
        message=f"Device flagged as lost by {user.email}",
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert
