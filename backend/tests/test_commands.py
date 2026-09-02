"""Commands: issue, poll, report, dedupe, and secure removal + revocation."""


def test_command_lifecycle(client, owner_headers, enrolled_device):
    did, dh = enrolled_device
    cmd = client.post(f"/devices/{did}/commands", headers=owner_headers,
                      json={"type": "ring"}).json()
    assert cmd["status"] == "pending"
    # Phone polls and sees it.
    pending = client.get("/device/commands", headers=dh).json()
    assert [c["type"] for c in pending] == ["ring"]
    # Phone reports completion.
    client.post(f"/device/commands/{cmd['id']}/result", headers=dh,
                json={"status": "completed", "result": "done"})
    hist = client.get(f"/devices/{did}/commands", headers=owner_headers).json()
    assert hist[0]["status"] == "completed"
    # No longer pending.
    assert client.get("/device/commands", headers=dh).json() == []


def test_duplicate_pending_command_blocked(client, owner_headers, enrolled_device):
    did, _ = enrolled_device
    assert client.post(f"/devices/{did}/commands", headers=owner_headers,
                       json={"type": "lock"}).status_code == 201
    assert client.post(f"/devices/{did}/commands", headers=owner_headers,
                       json={"type": "lock"}).status_code == 409


def test_secure_remove_revokes_token(client, owner_headers, enrolled_device):
    did, dh = enrolled_device
    # Token works before removal.
    assert client.get("/device/commands", headers=dh).status_code == 200
    cmd = client.post(f"/devices/{did}/commands", headers=owner_headers,
                      json={"type": "remove"}).json()
    client.post(f"/device/commands/{cmd['id']}/result", headers=dh,
                json={"status": "completed", "result": "uninstalled"})
    # Device is removed and its token is now rejected.
    assert client.get(f"/devices/{did}", headers=owner_headers).json()["status"] == "removed"
    assert client.get("/device/commands", headers=dh).status_code == 401
    assert client.post("/beacons", headers=dh,
                       json={"latitude": 1, "longitude": 1}).status_code == 401


def test_owner_cannot_command_others_device(client, admin_headers, owner_headers, enrolled_device):
    did, _ = enrolled_device
    client.post("/auth/owners", headers=admin_headers,
                json={"email": "c@test.com", "password": "password1"})
    ct = client.post("/auth/login", json={"email": "c@test.com", "password": "password1"}).json()["access_token"]
    r = client.post(f"/devices/{did}/commands", headers={"Authorization": f"Bearer {ct}"},
                    json={"type": "wipe"})
    assert r.status_code == 404
