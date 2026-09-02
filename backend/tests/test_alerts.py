"""Alerts: raising, listing, ack, mark-lost, evidence photos."""
from tests.conftest import make_png


def test_raise_and_list_alert(client, owner_headers, enrolled_device):
    did, dh = enrolled_device
    client.post("/alerts", headers=dh,
                json={"type": "sim_swap", "message": "New SIM", "new_sim_number": "+123"})
    alerts = client.get(f"/devices/{did}/alerts", headers=owner_headers).json()
    assert len(alerts) == 1
    assert alerts[0]["type"] == "sim_swap"
    assert alerts[0]["acknowledged"] is False


def test_acknowledge_alert(client, owner_headers, enrolled_device):
    did, dh = enrolled_device
    a = client.post("/alerts", headers=dh, json={"type": "failed_unlock"}).json()
    r = client.post(f"/alerts/{a['id']}/ack", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["acknowledged"] is True


def test_mark_lost(client, owner_headers, enrolled_device):
    did, _ = enrolled_device
    assert client.post(f"/devices/{did}/lost", headers=owner_headers).status_code == 201
    assert client.get(f"/devices/{did}", headers=owner_headers).json()["status"] == "lost"


def test_device_cannot_list_alerts(client, enrolled_device):
    did, dh = enrolled_device
    assert client.get(f"/devices/{did}/alerts", headers=dh).status_code == 401


def test_evidence_photo_roundtrip(client, owner_headers, enrolled_device):
    did, dh = enrolled_device
    a = client.post("/alerts", headers=dh, json={"type": "failed_unlock"}).json()
    # Device uploads a photo.
    up = client.post(f"/device/alerts/{a['id']}/photo", headers=dh,
                     files={"file": ("e.png", make_png(), "image/png")})
    assert up.status_code == 200
    assert up.json()["photo_url"] == f"/alerts/{a['id']}/photo"
    # Owner retrieves it.
    got = client.get(f"/alerts/{a['id']}/photo", headers=owner_headers)
    assert got.status_code == 200
    assert got.content.startswith(b"\x89PNG")


def test_evidence_photo_rejects_non_image(client, enrolled_device):
    _, dh = enrolled_device
    a = client.post("/alerts", headers=dh, json={"type": "failed_unlock"}).json()
    up = client.post(f"/device/alerts/{a['id']}/photo", headers=dh,
                     files={"file": ("x.txt", b"not an image", "text/plain")})
    assert up.status_code == 400


def test_evidence_photo_access_controlled(client, admin_headers, enrolled_device):
    did, dh = enrolled_device
    a = client.post("/alerts", headers=dh, json={"type": "failed_unlock"}).json()
    client.post(f"/device/alerts/{a['id']}/photo", headers=dh,
                files={"file": ("e.png", make_png(), "image/png")})
    # A different owner must not fetch the photo.
    client.post("/auth/owners", headers=admin_headers,
                json={"email": "nosy@test.com", "password": "password1"})
    nt = client.post("/auth/login", json={"email": "nosy@test.com", "password": "password1"}).json()["access_token"]
    assert client.get(f"/alerts/{a['id']}/photo",
                      headers={"Authorization": f"Bearer {nt}"}).status_code == 404
