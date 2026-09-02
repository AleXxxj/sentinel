# Sentinel — Consent-Based Anti-Theft Platform

Sentinel is a **multi-tenant, consent-based anti-theft platform** for phones (and, later,
laptops). It is **not** spyware: every enrolled device is registered by its owner, the app is
visible on the device, and the owner can always remove it through a secure, owner-only process.

## What it does

- **Location beaconing** — an enrolled device periodically reports its location so the owner can
  see it on a map, even when the phone is not physically with them.
- **SIM-swap alerts** (Phase 2) — if the SIM changes, the new number + location is sent to a
  backup contact.
- **Evidence capture** (Phase 2) — a photo + location on repeated failed unlocks.
- **Fleet management** — a role hierarchy so one operator (super admin) can oversee many owners,
  and each owner sees only their own device(s).

## Role hierarchy

| Role          | Can see                              | Can do                                             |
|---------------|--------------------------------------|----------------------------------------------------|
| `super_admin` | Every owner and every device         | Manage owners, support, suspend                    |
| `owner`       | Only their own device(s) and data    | View data, request secure removal of the tool      |
| `device`      | Nothing (reports up only)            | Send beacons, alerts, evidence                     |

## Project layout

```
sentinel/
├── README.md
├── backend/            # FastAPI + SQLModel backend (Phase 1)
│   ├── requirements.txt
│   ├── .env.example
│   ├── seed.py         # creates the first super admin
│   └── app/
│       ├── main.py         # FastAPI app + router mounting
│       ├── config.py       # settings loaded from environment
│       ├── database.py     # DB engine + session
│       ├── security.py     # password hashing + JWT tokens
│       ├── models.py       # User / Device / Beacon tables
│       ├── schemas.py      # request/response shapes
│       ├── deps.py         # auth + role-gating dependencies
│       └── routers/
│           ├── auth.py     # login, create owner
│           ├── devices.py  # create/list devices, enroll
│           └── beacons.py  # ingest + query location beacons
└── docs/
    └── architecture.md
```

## Quick start (backend)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit SECRET_KEY
python seed.py                # creates the first super admin
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/docs for the interactive API explorer.

## Try it with no phone (dashboard + simulator)

With the server running, in a second terminal:

```bash
cd backend && source .venv/bin/activate
python demo.py                       # creates a demo owner + device, prints an enroll token
python simulator.py <ENROLL_TOKEN>   # a fake phone that moves and raises alerts
```

Then open http://127.0.0.1:8000/dashboard/ and log in as `john@client.com` / `johnpass123`
to watch it live on a map, with the alert feed lighting up.

## Run the tests

```bash
cd backend && source .venv/bin/activate
python -m pytest -q
```

## Roadmap

- **Phase 1 (done):** backend spine — auth/roles, enrollment, beaconing, owner API.
- **Phase 1.5 (done):** owner dashboard with live map + simulator; alerts backbone
  (SIM-swap, failed-unlock, powered-off, low-battery, mark-lost); super-admin fleet view.
- **Phase 1.6 (done):** command channel (ring/lock/wipe/remove) with owner-gated secure
  removal + device-token revocation; login brute-force lockout; change-password;
  input validation.
- **Phase 1.7 (done):** evidence-photo capture (upload + access-controlled retrieval);
  full pytest suite (`backend/tests/`).
- **Phase 1.8 (done):** production-ready — Alembic migrations, Docker + docker-compose,
  Postgres support, env-driven config. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
- **Phase 2 (next):** the real Android agent — enroll + beacon + generate the alerts on a
  real phone as Device Owner; capture failed-unlock evidence photos.
- **Phase 3:** super dashboard polish + secure owner-gated removal flow + remote lock (FCM).
- **Phase 4:** laptop agent. (iOS: use Apple Find My — it cannot be beaten by a third-party app.)
