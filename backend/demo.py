"""
One-command demo setup.

Talks to the running server, makes sure a demo owner + device exist, and prints
the enroll token plus the exact next command to run. Saves you clicking through
the API docs by hand.

Run (with the server running in another terminal):
    python demo.py
"""
import sys

import httpx

from app.config import settings

BASE = "http://127.0.0.1:8000"

OWNER_EMAIL = "john@client.com"
OWNER_PASSWORD = "johnpass123"


def main() -> None:
    c = httpx.Client(base_url=BASE, timeout=10.0)

    # Confirm the server is up.
    try:
        c.get("/health").raise_for_status()
    except Exception:
        print("Server is not reachable at", BASE)
        print("Start it first:  uvicorn app.main:app --reload")
        sys.exit(1)

    # 1) Log in as the super admin (credentials from .env).
    r = c.post("/auth/login", json={
        "email": settings.FIRST_SUPERADMIN_EMAIL,
        "password": settings.FIRST_SUPERADMIN_PASSWORD,
    })
    if r.status_code != 200:
        print("Super admin login failed. Did you run `python seed.py`?")
        print(r.text)
        sys.exit(1)
    admin = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # 2) Make sure the demo owner exists (ignore "already exists").
    r = c.post("/auth/owners", headers=admin, json={
        "email": OWNER_EMAIL, "password": OWNER_PASSWORD, "full_name": "John",
    })
    if r.status_code not in (201, 409):
        print("Could not create owner:", r.text)
        sys.exit(1)

    # 3) Log in as that owner and create a device.
    r = c.post("/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    owner = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = c.post("/devices", headers=owner, json={
        "name": "John's Fold 7", "platform": "android", "model": "SM-F966B",
    })
    if r.status_code != 201:
        print("Could not create device:", r.text)
        sys.exit(1)
    device = r.json()
    enroll_token = device["enroll_token"]

    print("=" * 64)
    print("Demo ready!")
    print("=" * 64)
    print(f"Owner login  : {OWNER_EMAIL} / {OWNER_PASSWORD}")
    print(f"Device       : {device['name']} (id {device['id']})")
    print(f"Enroll token : {enroll_token}")
    print()
    print("Next, start the fake phone in a NEW terminal (keep the server running):")
    print()
    print(f"    python simulator.py {enroll_token}")
    print()
    print("Then open the dashboard and log in as the owner above:")
    print()
    print("    http://127.0.0.1:8000/dashboard/")
    print("=" * 64)


if __name__ == "__main__":
    main()
