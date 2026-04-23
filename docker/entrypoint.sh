#!/usr/bin/env bash
# Parcel container entrypoint.

set -euo pipefail

cmd="${1:-serve}"

case "$cmd" in
  serve)
    exec uv run uvicorn --factory parcel_shell.app:create_app \
      --host "${PARCEL_HOST:-0.0.0.0}" \
      --port "${PARCEL_PORT:-8000}" \
      --reload
    ;;
  migrate)
    exec uv run alembic \
      -c packages/parcel-shell/src/parcel_shell/alembic.ini \
      upgrade head
    ;;
  shell)
    exec /bin/bash
    ;;
  *)
    echo "[parcel] Unknown command: $cmd"
    echo "Usage: $0 {serve|migrate|shell}"
    exit 1
    ;;
esac
