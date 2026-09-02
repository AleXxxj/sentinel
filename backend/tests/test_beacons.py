"""Beacons: submission, validation, retrieval, ownership."""


def test_submit_and_read_latest(client, owner_headers, enrolled_device):
    did, dh = enrolled_device
    r = client.post("/beacons", headers=dh,
                    json={"latitude": 6.5, "longitude": 3.3, "battery_pct": 55})
    assert r.status_code == 201
    latest = client.get(f"/devices/{did}/latest", headers=owner_headers).json()
    assert latest["latitude"] == 6.5
    assert latest["battery_pct"] == 55


def test_beacon_history(client, owner_headers, enrolled_device):
    did, dh = enrolled_device
    for i in range(3):
        client.post("/beacons", headers=dh, json={"latitude": i, "longitude": i})
    hist = client.get(f"/devices/{did}/beacons", headers=owner_headers).json()
    assert len(hist) == 3


def test_rejects_impossible_coordinates(client, enrolled_device):
    _, dh = enrolled_device
    assert client.post("/beacons", headers=dh, json={"latitude": 999, "longitude": 0}).status_code == 422
    assert client.post("/beacons", headers=dh, json={"latitude": 0, "longitude": 999}).status_code == 422


def test_rejects_bad_battery(client, enrolled_device):
    _, dh = enrolled_device
    assert client.post("/beacons", headers=dh,
                       json={"latitude": 0, "longitude": 0, "battery_pct": 500}).status_code == 422


def test_latest_requires_ownership(client, admin_headers, enrolled_device):
    did, dh = enrolled_device
    client.post("/beacons", headers=dh, json={"latitude": 1, "longitude": 1})
    # Create a second, unrelated owner who should get 404.
    client.post("/auth/owners", headers=admin_headers,
                json={"email": "other@test.com", "password": "password1"})
    ot = client.post("/auth/login", json={"email": "other@test.com", "password": "password1"}).json()["access_token"]
    assert client.get(f"/devices/{did}/latest",
                      headers={"Authorization": f"Bearer {ot}"}).status_code == 404
