#!/bin/sh
set -e

python /app/scripts/download_db.py

PORT="${PORT:-8000}"
exec uvicorn main:app --host 0.0.0.0 --port "$PORT"
