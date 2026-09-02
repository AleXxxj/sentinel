"""
Reusable FastAPI dependencies for authentication and authorization.

These turn the `Authorization: Bearer <token>` header into a real User or
Device object, and enforce role rules:

  - get_current_user   -> any logged-in human (super or owner)
  - require_super      -> super admins only
  - get_current_device -> an enrolled phone (device token)

Use them in endpoints with `Depends(...)`.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from .database import get_session
from .models import Device, DeviceStatus, Role, User
from .security import decode_token

# Reads the "Authorization: Bearer <token>" header.
bearer = HTTPBearer(auto_error=True)

SessionDep = Annotated[Session, Depends(get_session)]
CredsDep = Annotated[HTTPAuthorizationCredentials, Depends(bearer)]


def _unauthorized(detail: str = "Invalid or expired token") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def get_current_user(creds: CredsDep, session: SessionDep) -> User:
    """Resolve a human user from an 'access' token."""
    payload = decode_token(creds.credentials)
    if not payload or payload.get("typ") != "access":
        raise _unauthorized()

    user = session.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise _unauthorized("User not found or disabled")
    return user


def require_super(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Allow only super admins."""
    if user.role != Role.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin privileges required",
        )
    return user


def get_current_device(creds: CredsDep, session: SessionDep) -> Device:
    """Resolve an enrolled phone from a 'device' token.

    Rejects the token if the device was removed, or if its token_version was
    bumped since the token was issued (our revocation mechanism).
    """
    payload = decode_token(creds.credentials)
    if not payload or payload.get("typ") != "device":
        raise _unauthorized()

    device = session.get(Device, int(payload["sub"]))
    if not device:
        raise _unauthorized("Device not found")
    if device.status == DeviceStatus.removed:
        raise _unauthorized("Device has been removed")
    if payload.get("ver") != device.token_version:
        raise _unauthorized("Device token has been revoked")
    return device


# Handy aliases for endpoint signatures.
CurrentUser = Annotated[User, Depends(get_current_user)]
SuperUser = Annotated[User, Depends(require_super)]
CurrentDevice = Annotated[Device, Depends(get_current_device)]


def owner_can_access_device(user: User, device: Device) -> bool:
    """A super admin can access any device; an owner only their own."""
    return user.role == Role.super_admin or device.owner_id == user.id
