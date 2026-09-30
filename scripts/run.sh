#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Install dependencies and copy .env.example before starting; see README.
exec python -m uvicorn server.app:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --ws-max-size 65536
