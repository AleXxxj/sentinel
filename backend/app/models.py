"""
Database tables.

Three core tables in Phase 1:
  - User    : a human account, either a super admin or a device owner.
  - Device  : an enrolled phone, tied to exactly one owner.
  - Beacon  : one location report sent by a device.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Timezone-aware current UTC time (used as a default for timestamps)."""
    return datetime.now(timezone.utc)


class Role(str, Enum):
    """Who a user is. Devices are not users; they authenticate separately."""
    super_admin = "super_admin"
    owner = "owner"


class DeviceStatus(str, Enum):
    pending = "pending"      # created, but the phone has not enrolled yet
    active = "active"        # enrolled and reporting
    lost = "lost"            # owner flagged it as stolen/lost
    removed = "removed"      # tool removed through the secure flow


class AlertType(str, Enum):
    """The kinds of events the phone (or owner) can raise."""
    sim_swap = "sim_swap"            # a new SIM was inserted
    failed_unlock = "failed_unlock"  # repeated wrong unlock attempts (evidence)
    powered_off = "powered_off"      # phone is being shut down
    low_battery = "low_battery"      # battery critically low
    marked_lost = "marked_lost"      # owner flagged the device as lost/stolen


class CommandType(str, Enum):
    """Actions an owner/super can send down to a phone."""
    ring = "ring"          # play a loud sound to locate it
    lock = "lock"          # remotely lock the screen
    wipe = "wipe"          # factory-wipe the device (destructive)
    remove = "remove"      # release Device-Owner and uninstall the agent


class CommandStatus(str, Enum):
    pending = "pending"            # created, not yet picked up by the phone
    acknowledged = "acknowledged"  # phone received it, working on it
    completed = "completed"        # phone finished it
    failed = "failed"              # phone could not complete it


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    full_name: str = ""
    hashed_password: str
    role: Role = Field(default=Role.owner)
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class Device(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)

    name: str                                    # friendly label, e.g. "John's Fold 7"
    platform: str = "android"                    # android | windows | macos
    model: Optional[str] = None                  # e.g. "SM-F966B"
    imei: Optional[str] = Field(default=None, index=True)

    status: DeviceStatus = Field(default=DeviceStatus.pending)

    # One-time token the phone presents when it first enrolls.
    enroll_token: Optional[str] = Field(default=None, index=True)
    # Set once the phone has enrolled; used to detect double-enrollment.
    enrolled_at: Optional[datetime] = None

    # Bumped to invalidate all previously-issued device tokens (e.g. on removal
    # or a forced re-enroll). The device token carries this number; if it no
    # longer matches, the token is rejected.
    token_version: int = 0

    last_seen: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class Beacon(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id", index=True)

    latitude: float
    longitude: float
    accuracy_m: Optional[float] = None           # GPS accuracy radius in metres
    battery_pct: Optional[int] = None
    is_charging: Optional[bool] = None

    # When the phone recorded the fix, vs. when the server received it. These
    # differ when the phone was offline and buffered beacons to send later.
    recorded_at: datetime = Field(default_factory=utcnow)
    received_at: datetime = Field(default_factory=utcnow)


class Alert(SQLModel, table=True):
    """A notable event about a device: SIM swap, failed unlock, shutdown, etc."""
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id", index=True)

    type: AlertType
    message: str = ""

    # Optional context, depending on the alert type:
    latitude: Optional[float] = None          # where the phone was at the time
    longitude: Optional[float] = None
    new_sim_number: Optional[str] = None      # for sim_swap alerts
    photo_url: Optional[str] = None           # for failed_unlock evidence (later)

    # Owners acknowledge alerts so the dashboard can show "new" vs "seen".
    acknowledged: bool = False

    created_at: datetime = Field(default_factory=utcnow)


class Command(SQLModel, table=True):
    """An instruction issued by an owner/super for a phone to carry out."""
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="device.id", index=True)

    type: CommandType
    status: CommandStatus = Field(default=CommandStatus.pending)
    issued_by: int = Field(foreign_key="user.id")   # which user sent it
    result: str = ""                                 # phone's report back

    created_at: datetime = Field(default_factory=utcnow)
    completed_at: Optional[datetime] = None
