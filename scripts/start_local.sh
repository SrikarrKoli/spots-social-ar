#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Set APP_CAMERA_INDEX and APP_TRANSCRIPTION_PROVIDER before using voice."
fi
# The Kokoro assistant voice needs a system eSpeak NG on macOS.
if ! command -v espeak-ng >/dev/null 2>&1; then
  echo "Installing espeak-ng for the Kokoro assistant voice…"
  brew install espeak-ng || echo "espeak-ng is missing; the assistant will use the browser voice."
fi
uv sync --extra voice --inexact
npm --prefix frontend install --include=dev
npm --prefix frontend run build
exec uv run --extra voice uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --env-file .env --no-access-log
