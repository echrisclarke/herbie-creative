#!/usr/bin/env bash
# Stop Herbie Creative (macOS / Linux)
set -euo pipefail
pkill -f "uvicorn app.main:app" 2>/dev/null || true
# Fallback: anything listening on 8000
if command -v lsof >/dev/null 2>&1; then
  pids=$(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true)
  if [[ -n "${pids}" ]]; then
    kill ${pids} 2>/dev/null || true
  fi
fi
echo "Herbie Creative stopped (if it was running)."
