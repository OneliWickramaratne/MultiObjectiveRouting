#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python scripts/migrate.py bootstrap
fi

exec python -m uvicorn app.main:app \
    --host "${API_HOST:-0.0.0.0}" \
    --port "${API_PORT:-8001}" \
    --workers "${API_WORKERS:-1}"
