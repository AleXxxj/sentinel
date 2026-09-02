"""
Request and response shapes (Pydantic models).

These are separate from the database tables so we can control exactly what goes
in and out of the API — for example, we never send `hashed_password` back to a
client, and the enroll token is only ever returned once, at creation time.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from .models import AlertType, CommandStatus, CommandType, DeviceStatus, Role


# --- Auth ---

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role


class CreateOwnerRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


# --- Devices ---

class CreateDeviceRequest(BaseModel):
    name: str
    platform: str = "android"
    model: Optional[str] = None
    imei: Optional[str] = None
    # Super admins may create a device for a specific owner; owners create for
    # themselves and leave this unset.
    owner_id: Optional[int] = None


class DeviceResponse(BaseModel):
    id: int
    owner_id: int
    name: str
    platform: str
    model: Optional[str]
    imei: Optional[str]
    status: DeviceStatus
    last_seen: Optional[datetime]
    created_at: datetime
    # Filled in for super admins so they can see whose phone this is.
    owner_email: Optional[str] = None


class CreateDeviceResponse(DeviceResponse):
    # Only returned once, at creation. The phone needs this to enroll.
    enroll_token: str


# --- Enrollment (device -> server) ---

class EnrollRequest(BaseModel):
    enroll_token: str
    model: Optional[str] = None
    imei: Optional[str] = None


class EnrollResponse(BaseModel):
    device_id: int
    device_token: str      # long-lived token the phone uses to send beacons


# --- Beacons ---

class BeaconIn(BaseModel):
    # Reject physically impossible coordinates and battery values.
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: Optional[float] = Field(default=None, ge=0)
    battery_pct: Optional[int] = Field(default=None, ge=0, le=100)
    is_charging: Optional[bool] = None
    recorded_at: Optional[datetime] = None   # phone's own timestamp, if buffered


class BeaconResponse(BaseModel):
    id: int
    device_id: int
    latitude: float
    longitude: float
    accuracy_m: Optional[float]
    battery_pct: Optional[int]
    is_charging: Optional[bool]
    recorded_at: datetime
    received_at: datetime


# --- Alerts ---

class AlertIn(BaseModel):
    """Sent by the phone when something notable happens."""
    type: AlertType
    message: str = Field(default="", max_length=500)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    new_sim_number: Optional[str] = Field(default=None, max_length=40)
    photo_url: Optional[str] = Field(default=None, max_length=1000)


class AlertResponse(BaseModel):
    id: int
    device_id: int
    type: AlertType
    message: str
    latitude: Optional[float]
    longitude: Optional[float]
    new_sim_number: Optional[str]
    photo_url: Optional[str]
    acknowledged: bool
    created_at: datetime


# --- Commands ---

class CommandCreate(BaseModel):
    type: CommandType


class CommandResultIn(BaseModel):
    """The phone reporting back on a command."""
    status: CommandStatus
    result: str = Field(default="", max_length=500)


class CommandResponse(BaseModel):
    id: int
    device_id: int
    type: CommandType
    status: CommandStatus
    issued_by: int
    result: str
    created_at: datetime
    completed_at: Optional[datetime]


# --- Account ---

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)
