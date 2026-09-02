"""
Shared pytest fixtures.

We point the app at a throwaway SQLite database and evidence folder in a temp
directory (set BEFORE importing the app, so the module-level engine picks them
up), then rebuild the schema fresh for every test.
"""
import os
import tempfile

# Must be set before importing anything under `app`.
_TMP = tempfile.mkdtemp(prefix="sentinel_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["EVIDENCE_DIR"] = f"{_TMP}/evidence"
os.environ["SECRET_KEY"] = "test-secret-key"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.security import hash_password  # noqa: E402

ADMIN = ("admin@test.com", "adminpass")


@pytest.fixture(autouse=True)
def fresh_db():
    """Drop and recreate all tables before each test, seeded with a super admin."""
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(User(email=ADMIN[0], hashed_password=hash_password(ADMIN[1]), role=Role.super_admin))
        s.commit()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(client):
    r = client.post("/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
    return _headers(r.json()["access_token"])


@pytest.fixture
def owner_headers(client, admin_headers):
    """Create an owner and return their auth headers."""
    client.post("/auth/owners", headers=admin_headers,
                json={"email": "owner@test.com", "password": "ownerpass", "full_name": "Owner"})
    r = client.post("/auth/login", json={"email": "owner@test.com", "password": "ownerpass"})
    return _headers(r.json()["access_token"])


@pytest.fixture
def enrolled_device(client, owner_headers):
    """Create + enroll a device. Returns (device_id, device_headers)."""
    dev = client.post("/devices", headers=owner_headers, json={"name": "Test Phone"}).json()
    token = client.post("/devices/enroll",
                        json={"enroll_token": dev["enroll_token"]}).json()["device_token"]
    return dev["id"], _headers(token)


def make_png() -> bytes:
    """A tiny valid 2x2 red PNG for evidence-upload tests."""
    import struct
    import zlib

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    row = b"\x00" + b"\xc8\x3c\x3c" * 2
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(row * 2)) + chunk(b"IEND", b""))
