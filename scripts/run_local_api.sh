#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  umask 077
  printf 'PKSCREENER_API_TOKEN=%s\n' "$(openssl rand -hex 32)" > "$ENV_FILE"
fi

TOKEN="$(sed -n 's/^PKSCREENER_API_TOKEN=//p' "$ENV_FILE" | tail -n 1)"
if [ -z "$TOKEN" ] || [ "$TOKEN" = "replace-with-a-random-local-secret" ]; then
  echo "Set PKSCREENER_API_TOKEN in .env to a unique random value." >&2
  exit 1
fi

export PKSCREENER_API_TOKEN="$TOKEN"
cd "$ROOT_DIR"
API_PORT="${PKSCREENER_API_PORT:-8000}"
exec .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port "$API_PORT"
