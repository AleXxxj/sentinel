# Sentinel — Architecture (Phase 1)

## Overview

Sentinel is a consent-based, multi-tenant anti-theft platform. Phase 1 delivers the
**backend spine**: authentication with roles, device enrollment, and location beaconing.

```
┌──────────────────┐        HTTPS + JWT        ┌────────────────────┐
│  Android agent    │  ── beacons / alerts ──▶  │   Backend API       │
│ (Device Owner)    │  ◀── commands ─────────    │  FastAPI + SQLModel │
└──────────────────┘                            │  SQLite / Postgres  │
                                                └─────────┬──────────┘
                          ┌──────────────────────────────┼────────────────────┐
                          ▼                               ▼                     ▼
                   Super dashboard                 Owner dashboard      Secure remove flow
                   (all tenants)                   (own device only)    (owner-only, Phase 3)
```

## Authentication model

Two token types, distinguished by the `typ` claim inside the JWT:

| Token type | Issued to        | How obtained                    | Used for                        |
|------------|------------------|----------------------------------|----------------------------------|
| `access`   | super / owner    | `POST /auth/login`               | all dashboard/API calls          |
| `device`   | an enrolled phone| `POST /devices/enroll`           | submitting beacons/alerts        |

A `device` token can never act as a user, and vice versa — enforced in `deps.py`.

## Role rules

- **super_admin** — sees and manages everything; can create owners and create devices
  for any owner.
- **owner** — sees only devices where `device.owner_id == user.id`; can create devices
  for themselves only.
- **device** — has no read access; it can only push beacons/alerts about itself.

## Enrollment flow (how a phone joins)

1. An owner (or super admin) calls `POST /devices` → server returns a **one-time
   `enroll_token`**.
2. That token is handed to the phone (typed in, or via QR code during setup).
3. The phone calls `POST /devices/enroll` with the token → server marks the device
   `active`, consumes the token, and returns a long-lived **device token**.
4. The phone stores the device token and uses it to `POST /beacons`.

The `enroll_token` is single-use: once enrolled, it is cleared, so it cannot be replayed.

## Data model

- **User**: `id, email, full_name, hashed_password, role, is_active, created_at`
- **Device**: `id, owner_id→User, name, platform, model, imei, status, enroll_token,
  enrolled_at, last_seen, created_at`
- **Beacon**: `id, device_id→Device, latitude, longitude, accuracy_m, battery_pct,
  is_charging, recorded_at, received_at`

`recorded_at` vs `received_at` lets us handle offline buffering: a phone with no signal
stores fixes locally and uploads them later; we keep both the original fix time and the
time the server got it.

## Security notes / decisions

- Passwords: bcrypt, never stored in plain text.
- Enroll tokens and device secrets: generated with `secrets.token_urlsafe`.
- Error messages avoid leaking which emails exist (login) or which devices exist
  (404 instead of 403 for devices a user may not see).
- **Removal** (Phase 3): the app on the phone will only release its Device-Owner lock
  after the backend confirms an *owner-authenticated* removal request. This is the
  "unique process known only to the owner" — visible and legitimate, never covert.

## Alerts (theft-feature backbone)

Beyond location, a device can raise **alerts** — the events that matter when a phone is
stolen. The backend stores and serves them; the Android agent will generate them for real
(the simulator generates them for now).

Alert types: `sim_swap`, `failed_unlock`, `powered_off`, `low_battery`, `marked_lost`.

Endpoints:

| Method + path                     | Who    | Purpose                              |
|-----------------------------------|--------|--------------------------------------|
| `POST /alerts`                    | device | phone raises an alert                |
| `GET  /devices/{id}/alerts`       | user   | list a device's alerts (newest first)|
| `POST /alerts/{id}/ack`           | user   | mark an alert acknowledged           |
| `POST /devices/{id}/lost`         | owner  | flag device lost; logs an alert      |

Super admins additionally see `owner_email` on each device in `GET /devices`, so the fleet
view shows whose phone each one is.

## Command channel + secure removal

Owners send **commands** down to a phone; the phone polls, executes, and reports back. The
agent never acts on its own — this is the "unique process only the owner controls."

Command types: `ring`, `lock`, `wipe`, `remove`.

| Method + path                          | Who    | Purpose                             |
|----------------------------------------|--------|-------------------------------------|
| `POST /devices/{id}/commands`          | user   | issue a command                     |
| `GET  /devices/{id}/commands`          | user   | command history                     |
| `GET  /device/commands`                | device | poll for pending commands           |
| `POST /device/commands/{id}/result`    | device | report a command's outcome          |

**Secure removal + token revocation.** When the phone reports a `remove` command
`completed`, the backend marks the device `removed` and increments `Device.token_version`.
Every device token embeds the version it was issued under (`ver` claim); once the version
changes, all old tokens are rejected in `get_current_device`. So a removed (or re-enrolled)
phone's token stops working immediately — there is no 10-year window of a live orphaned
token.

## Database migrations (important gotcha)

`init_db()` calls `SQLModel.metadata.create_all()`, which creates **missing tables** but
**never alters existing ones**. So when we add a *column* to an existing table (e.g.
`Device.token_version`), an already-created dev database won't get it, and inserts fail with
"no such column". Two ways to handle it:

- **Dev shortcut**: delete `sentinel.db` and re-run `seed.py` (wipes data), or
  `ALTER TABLE ... ADD COLUMN ...` by hand for a single column.
- **Production**: use **Alembic** for real versioned migrations. This is a Phase 3 to-do
  before any real deployment.

## Security hardening

- **Device-token revocation** via `token_version` (above); removed devices are also
  rejected outright.
- **Login brute-force protection**: 5 failed logins per email triggers a 5-minute lockout
  (in-memory; move to Redis for multi-server). Successful login clears the counter.
- **Change password**: `POST /auth/change-password` (verifies the old password; new password
  must be ≥ 8 chars).
- **Input validation**: beacons/alerts reject impossible coordinates (lat ±90, lng ±180),
  negative accuracy, and battery outside 0–100; string fields are length-capped.

## Evidence photos

Failed-unlock alerts can carry a **photo** (the front-camera shot of whoever is holding the
phone). The pipeline:

| Method + path                          | Who    | Purpose                                  |
|----------------------------------------|--------|------------------------------------------|
| `POST /device/alerts/{id}/photo`       | device | upload a JPEG/PNG for an alert (multipart)|
| `GET  /alerts/{id}/photo`              | user   | download it (owner-gated)                |

- Uploads are validated by **magic bytes** (must really be JPEG/PNG) and capped at
  `MAX_PHOTO_BYTES` (5 MB).
- Files are stored in `EVIDENCE_DIR` (default `./evidence`), deliberately **outside** the
  public static folder. They are served only through the authenticated, ownership-checked
  `GET /alerts/{id}/photo` — never as a guessable public URL.

## Testing

A pytest suite lives in `backend/tests/`, covering auth, devices, beacons, alerts, commands,
and security rules (tenant isolation, token separation, revocation, brute-force lockout,
evidence access control). Each test runs against a fresh throwaway SQLite database.

```bash
cd backend && source .venv/bin/activate
python -m pytest -q
```

## The dashboard + simulator (how to see it work without a phone)

- **Dashboard**: static web app at `GET /dashboard/` — login, device list, live map,
  telemetry, alert feed, "report lost". Served from `app/static/index.html`.
- **Simulator** (`simulator.py`): a stand-in "phone" that enrolls and beacons a moving
  location, and occasionally raises SIM-swap / failed-unlock alerts. Replaced by the real
  Android agent later.
- **`demo.py`**: one command to create a demo owner + device and print the enroll token.

## What is intentionally NOT done yet

- The real **Android agent** (Phase 2) — the simulator stands in for it.
- **Evidence photos** — the `Alert.photo_url` field exists, but capturing/storing the image
  is Phase 2 (Android) + file storage.
- **Push-to-device command channel** (Phase 3, via FCM) — e.g. remote lock/wipe.
- **Secure owner-gated removal** flow (Phase 3).
