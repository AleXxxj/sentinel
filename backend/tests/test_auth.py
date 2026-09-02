"""Auth: login, roles, change-password, brute-force lockout."""


def test_login_success(client, admin_headers):
    r = client.get("/auth/me", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["role"] == "super_admin"


def test_login_wrong_password(client):
    r = client.post("/auth/login", json={"email": "admin@test.com", "password": "nope"})
    assert r.status_code == 401


def test_login_unknown_email(client):
    r = client.post("/auth/login", json={"email": "ghost@test.com", "password": "x"})
    assert r.status_code == 401


def test_only_super_creates_owners(client, owner_headers):
    # An owner must not be able to create other owners.
    r = client.post("/auth/owners", headers=owner_headers,
                    json={"email": "x@test.com", "password": "password1"})
    assert r.status_code == 403


def test_duplicate_owner_rejected(client, admin_headers):
    body = {"email": "dup@test.com", "password": "password1"}
    assert client.post("/auth/owners", headers=admin_headers, json=body).status_code == 201
    assert client.post("/auth/owners", headers=admin_headers, json=body).status_code == 409


def test_change_password(client, owner_headers):
    assert client.post("/auth/change-password", headers=owner_headers,
                       json={"old_password": "wrong", "new_password": "newpass12"}).status_code == 400
    assert client.post("/auth/change-password", headers=owner_headers,
                       json={"old_password": "ownerpass", "new_password": "newpass12"}).status_code == 204
    # Old password no longer works; new one does.
    assert client.post("/auth/login", json={"email": "owner@test.com", "password": "ownerpass"}).status_code == 401
    assert client.post("/auth/login", json={"email": "owner@test.com", "password": "newpass12"}).status_code == 200


def test_change_password_min_length(client, owner_headers):
    r = client.post("/auth/change-password", headers=owner_headers,
                    json={"old_password": "ownerpass", "new_password": "short"})
    assert r.status_code == 422


def test_brute_force_lockout(client):
    codes = [client.post("/auth/login", json={"email": "target@test.com", "password": "x"}).status_code
             for _ in range(6)]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429
