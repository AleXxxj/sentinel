"""
Authentication + user management endpoints.

  POST /auth/login          -> exchange email+password for an access token
  GET  /auth/me             -> who am I (from my token)
  POST /auth/owners         -> super admin creates a new owner account
  GET  /auth/owners         -> super admin lists all owners
"""
import time

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from ..deps import CurrentUser, SessionDep, SuperUser
from ..models import Role, User
from ..schemas import (
    ChangePasswordRequest,
    CreateOwnerRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
)
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


# --- Simple in-memory login throttling (brute-force protection) ---
# For a single server this is fine. In a multi-server deployment, move this to
# Redis so the counter is shared. Keyed by email.
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300
_failed: dict[str, list] = {}   # email -> [count, first_attempt_ts]


def _check_locked(email: str) -> None:
    rec = _failed.get(email)
    if not rec:
        return
    count, first_ts = rec
    if count >= _MAX_ATTEMPTS and (time.time() - first_ts) < _LOCKOUT_SECONDS:
        wait = int(_LOCKOUT_SECONDS - (time.time() - first_ts))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {wait} seconds.",
        )


def _record_failure(email: str) -> None:
    rec = _failed.get(email)
    if not rec or (time.time() - rec[1]) >= _LOCKOUT_SECONDS:
        _failed[email] = [1, time.time()]
    else:
        rec[0] += 1


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: SessionDep):
    _check_locked(body.email)

    user = session.exec(select(User).where(User.email == body.email)).first()
    if not user or not verify_password(body.password, user.hashed_password):
        _record_failure(body.email)
        # Same error whether the email or the password was wrong, so we don't
        # leak which emails exist.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    _failed.pop(body.email, None)   # clear counter on success
    token = create_access_token(user_id=user.id, role=user.role.value)
    return TokenResponse(access_token=token, role=user.role)


@router.post("/change-password", status_code=204)
def change_password(body: ChangePasswordRequest, user: CurrentUser, session: SessionDep):
    if not verify_password(body.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    session.add(user)
    session.commit()


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser):
    return user


@router.post("/owners", response_model=UserResponse, status_code=201)
def create_owner(body: CreateOwnerRequest, _super: SuperUser, session: SessionDep):
    existing = session.exec(select(User).where(User.email == body.email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    owner = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=Role.owner,
    )
    session.add(owner)
    session.commit()
    session.refresh(owner)
    return owner


@router.get("/owners", response_model=list[UserResponse])
def list_owners(_super: SuperUser, session: SessionDep):
    return session.exec(select(User).where(User.role == Role.owner)).all()
