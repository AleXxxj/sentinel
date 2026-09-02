"""Devices: creation, enrollment, tenancy, token separation."""


def test_create_and_enroll(client, owner_headers):
    dev = client.post("/devices", headers=owner_headers, json={"name": "P"}).json()
    assert dev["status"] == "pending"
    assert dev["enroll_token"]
    r = client.post("/devices/enroll", json={"enroll_token": dev["enroll_token"]})
    assert r.status_code == 200
    assert r.json()["device_token"]


def test_enroll_token_is_single_use(client, owner_headers):
    dev = client.post("/devices", headers=owner_headers, json={"name": "P"}).json()
    tok = dev["enroll_token"]
    assert client.post("/devices/enroll", json={"enroll_token": tok}).status_code == 200
    # Replaying the same token must fail: it was consumed (cleared to None),
    # so the second attempt sees an unknown token -> 400.
    assert client.post("/devices/enroll", json={"enroll_token": tok}).status_code == 400


def test_invalid_enroll_token(client):
    assert client.post("/devices/enroll", json={"enroll_token": "bogus"}).status_code == 400


def test_tenant_isolation(client, admin_headers, owner_headers):
    # Owner A's device is invisible to owner B.
    dev = client.post("/devices", headers=owner_headers, json={"name": "A"}).json()
    client.post("/auth/owners", headers=admin_headers,
                json={"email": "b@test.com", "password": "password1"})
    b_tok = client.post("/auth/login", json={"email": "b@test.com", "password": "password1"}).json()["access_token"]
    bh = {"Authorization": f"Bearer {b_tok}"}
    assert client.get(f"/devices/{dev['id']}", headers=bh).status_code == 404
    assert client.get("/devices", headers=bh).json() == []


def test_super_sees_owner_email(client, admin_headers, owner_headers):
    client.post("/devices", headers=owner_headers, json={"name": "P"})
    devices = client.get("/devices", headers=admin_headers).json()
    assert devices[0]["owner_email"] == "owner@test.com"


def test_device_token_not_valid_as_user(client, enrolled_device):
    _, dh = enrolled_device
    assert client.get("/auth/me", headers=dh).status_code == 401
