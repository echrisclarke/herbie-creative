#!/usr/bin/env bash
# Herbie Creative Quick start (macOS / Linux)
# Downloads to Desktop, ensures Python 3.12+, starts the app.
set -euo pipefail

DESKTOP="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
cd "${DESKTOP:-$HOME/Desktop}"

py_ok() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null
}

pick_py() {
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && py_ok "$(command -v "$c")"; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

echo "Checking for Python 3.12+..."
if ! PY="$(pick_py)"; then
  echo "Python 3.12+ not found. Trying to install..."
  if [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
    brew install python@3.12
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3.12 python3.12-venv python3-pip \
      || sudo apt-get install -y python3 python3-venv python3-pip
  else
    echo "Could not auto-install. Open https://www.python.org/downloads/ then run this again."
    command -v open >/dev/null 2>&1 && open "https://www.python.org/downloads/" || true
    command -v xdg-open >/dev/null 2>&1 && xdg-open "https://www.python.org/downloads/" || true
    exit 1
  fi
  if ! PY="$(pick_py)"; then
    echo "Python install finished, but 3.12+ is still not on PATH. Open a new terminal and run this again."
    exit 1
  fi
fi
echo "Python OK: $PY"

if [ ! -f herbie-creative/run_app.py ]; then
  echo "Downloading Herbie Creative..."
  curl -fsSL -o herbie-creative.zip https://github.com/echrisclarke/herbie-creative/archive/refs/heads/main.zip
  unzip -o herbie-creative.zip
  rm -rf herbie-creative
  mv herbie-creative-main herbie-creative
  rm -f herbie-creative.zip
fi

cd herbie-creative
echo "Starting app (leave this window open)..."
exec "$PY" run_app.py
