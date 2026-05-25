#!/usr/bin/env bash
set -euo pipefail

: "${APP_HOST:=0.0.0.0}"
: "${APP_PORT:=8000}"
: "${APP_WORKERS:=1}"
: "${APP_ENV:=development}"

echo "🚀 Starting FitAI Backend — env=$APP_ENV workers=$APP_WORKERS"

if [[ "$APP_ENV" == "production" ]]; then
  exec uvicorn api.main:app \
    --host "$APP_HOST" \
    --port "$APP_PORT" \
    --workers "$APP_WORKERS" \
    --no-access-log
else
  exec uvicorn api.main:app \
    --host "$APP_HOST" \
    --port "$APP_PORT" \
    --reload \
    --log-level debug
fi
