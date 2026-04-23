#!/usr/bin/env bash
# Parcel container entrypoint.
# Phase 0: placeholder. Phase 1 will wire real commands.

set -euo pipefail

cmd="${1:-serve}"

case "$cmd" in
  serve)
    echo "[parcel] Phase 0 scaffold — shell not yet implemented. Sleeping."
    # Phase 1 will replace with:
    # exec uv run uvicorn parcel_shell.app:app --host 0.0.0.0 --port 8000 --reload
    exec sleep infinity
    ;;
  migrate)
    echo "[parcel] Phase 0 scaffold — migrations not yet implemented."
    exit 0
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
