#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Set APP_CAMERA_INDEX and APP_TRANSCRIPTION_PROVIDER before using voice."
fi
uv sync --inexact
npm --prefix frontend install --include=dev
npm --prefix frontend run build
exec uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --env-file .env --no-access-log
