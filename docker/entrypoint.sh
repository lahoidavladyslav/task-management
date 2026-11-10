#!/bin/sh
set -e

# Set RUN_MIGRATIONS=false when migrations are applied by a separate step (several replicas).
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    alembic upgrade head
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
