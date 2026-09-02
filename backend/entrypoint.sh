#!/bin/sh
# Container startup: apply database migrations, then run the API server.
set -e

echo "Applying database migrations..."
alembic upgrade head

# Create the first super admin from the FIRST_SUPERADMIN_* env vars if it does
# not exist yet. seed.py is idempotent, so this is safe on every deploy. This
# matters on hosts (like Render's free tier) that offer no shell to run it by hand.
echo "Ensuring super admin exists..."
python seed.py || echo "Seed step skipped (continuing to start server)."

echo "Starting Sentinel API..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
