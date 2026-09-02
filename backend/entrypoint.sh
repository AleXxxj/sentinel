#!/bin/sh
# Container startup: apply database migrations, then run the API server.
set -e

echo "Applying database migrations..."
alembic upgrade head

echo "Starting Sentinel API..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
