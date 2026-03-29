#!/usr/bin/env bash
# Run the API from backend/ so Uvicorn's file watcher only sees app code — not .venv.
# (See SETUP_GUIDE.txt section 8 — required for stable /analyze on macOS/Linux.)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
