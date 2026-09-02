# Deploying the Sentinel backend

This guide takes the backend from "runs on my Mac" to "reachable by a real phone
on the internet." There are two paths: test the production stack locally first
(optional but recommended), then deploy to a host.

The app is containerized, and the container **runs database migrations
automatically on startup** (`alembic upgrade head`) before serving traffic.

---

## What you need

- A **GitHub account** (to hold the code the host deploys from).
- A host account — this guide uses **Render** (has a free tier, beginner-friendly).
- Optional: **Docker Desktop**, only if you want to test the full stack on your Mac first.

> You perform the account creation and deploy steps yourself — they need your login
> and possibly payment details, which I can't enter for you.

---

## Step 1 (optional): test the production stack locally with Docker

This runs the API against a **real PostgreSQL** database on your machine, exactly like
production, so you catch issues before paying for hosting.

```bash
# from the sentinel/ project root
docker compose up --build
```

Then, in a second terminal, create the first admin:

```bash
docker compose run --rm api python seed.py
```

Open http://localhost:8000/dashboard/ and log in with the admin credentials from
`docker-compose.yml` (`admin@example.com` / `change-me-now`). Stop it with `Ctrl+C`,
and `docker compose down` to remove the containers.

---

## Step 2: put the code on GitHub

The project isn't a git repo yet. From the `sentinel/` root:

```bash
git init
git add .
git commit -m "Sentinel backend"
```

Create an empty repo on GitHub, then:

```bash
git remote add origin https://github.com/<you>/sentinel.git
git branch -M main
git push -u origin main
```

The `.gitignore` already keeps secrets (`.env`), databases, and `evidence/` out of the repo.

---

## Step 3: deploy to Render

1. Sign in at https://render.com and connect your GitHub account.
2. **New → Blueprint**, and pick your `sentinel` repo. Render reads `render.yaml` and
   proposes: a **web service** (the API) + a **PostgreSQL database**.
3. It will prompt you for the two secret values:
   - `FIRST_SUPERADMIN_EMAIL` — your admin login email.
   - `FIRST_SUPERADMIN_PASSWORD` — a strong password.
   (`SECRET_KEY` is auto-generated; `DATABASE_URL` is wired to the database automatically.)
4. Click **Apply**. Render builds the Docker image, runs migrations, and starts the API.
   Your URL will look like `https://sentinel-api.onrender.com`.

### Create the super admin (one-off)

Migrations create the tables, but not the admin account. In the Render service's
**Shell** tab, run:

```bash
python seed.py
```

(Or trigger it however your host runs one-off commands.)

### Verify

- `https://<your-app>.onrender.com/health` → `{"status":"ok"}`
- `https://<your-app>.onrender.com/dashboard/` → log in as your admin.

---

## Step 4: lock down CORS (recommended)

Once you know your dashboard URL, set the `CORS_ORIGINS` env var on the service to that
exact origin (e.g. `https://sentinel-api.onrender.com`) instead of `*`, and redeploy.

---

## Later: changing the database schema

Because Alembic now owns the schema, adding/altering a model is a two-step routine — no
more "missing column" surprises:

```bash
# after editing app/models.py
cd backend && source .venv/bin/activate
alembic revision --autogenerate -m "describe your change"   # creates a migration
alembic upgrade head                                        # applies it locally
```

Commit the new file under `migrations/versions/`. On the next deploy, the container runs
`alembic upgrade head` automatically and applies it in production too.

---

## Other hosts

The container is standard, so it also runs on Fly.io, Railway, a VPS with Docker, etc.
Each just needs the same environment variables: `DATABASE_URL`, `SECRET_KEY`,
`ENVIRONMENT=production`, `CORS_ORIGINS`, and the two `FIRST_SUPERADMIN_*` values for the
initial seed.
