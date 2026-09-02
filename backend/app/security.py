"""
Security helpers: password hashing and JWT tokens.

- Passwords are hashed with bcrypt (never stored in plain text).
- Tokens are signed JWTs. We issue two kinds:
    * "access" tokens for human users (super/owner), carrying their role.
    * "device" tokens for enrolled phones, carrying the device id.
  The `typ` claim distinguishes them so a device token can never be used as a
  user token, or vice versa.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt

from .config import settings


# --- Passwords ---

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


# --- Tokens ---

def _create_token(subject: str, token_type: str, expires: timedelta, **extra: Any) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,       # who the token is about (user id or device id)
        "typ": token_type,    # "access" or "device"
        "iat": now,
        "exp": now + expires,
        **extra,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: int, role: str) -> str:
    return _create_token(
        subject=str(user_id),
        token_type="access",
        expires=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        role=role,
    )


def create_device_token(device_id: int, token_version: int) -> str:
    return _create_token(
        subject=str(device_id),
        token_type="device",
        expires=timedelta(days=settings.DEVICE_TOKEN_EXPIRE_DAYS),
        ver=token_version,   # lets us revoke by bumping the device's version
    )


def decode_token(token: str) -> Optional[dict]:
    """Return the token payload, or None if it is invalid or expired."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:
        return None
