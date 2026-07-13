#!/usr/bin/env bash
# Herbie Creative launcher (macOS / Linux)
set -euo pipefail
cd "$(dirname "$0")"

MIN_MAJOR=3
MIN_MINOR=12

open_url() {
  if command -v open >/dev/null 2>&1; then
    open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$1"
  else
    echo "Open $1 in your browser."
  fi
}

version_ok() {
  local exe="$1"
  local ver
  ver="$("$exe" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || true)"
  [[ -n "$ver" ]] || return 1
  local major minor
  IFS=. read -r major minor <<<"$ver"
  if (( major > MIN_MAJOR )); then return 0; fi
  if (( major < MIN_MAJOR )); then return 1; fi
  (( minor >= MIN_MINOR ))
}

pick_python() {
  local candidate
  if [[ -x "backend/.venv/bin/python" ]] && version_ok "backend/.venv/bin/python"; then
    echo "backend/.venv/bin/python"
    return 0
  fi
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && version_ok "$(command -v "$candidate")"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

try_install_python() {
  if [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
    echo "Installing Python 3.12 with Homebrew..."
    brew install python@3.12
    return 0
  fi
  if command -v apt-get >/dev/null 2>&1; then
    echo "Installing Python 3.12 with apt (may ask for sudo)..."
    sudo apt-get update
    sudo apt-get install -y python3.12 python3.12-venv python3-pip || sudo apt-get install -y python3 python3-venv python3-pip
    return 0
  fi
  return 1
}

if curl -sf "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
  echo "Herbie Creative is already running. Opening browser..."
  open_url "http://127.0.0.1:8000/"
  exit 0
fi

echo "Starting Herbie Creative..."
echo "Checking Python ${MIN_MAJOR}.${MIN_MINOR}+ ..."

PY=""
if PY="$(pick_python)"; then
  echo "Python OK ($PY)"
else
  echo "Python ${MIN_MAJOR}.${MIN_MINOR}+ was not found."
  if try_install_python; then
    if PY="$(pick_python)"; then
      echo "Python OK ($PY)"
    else
      echo "Python install finished, but ${MIN_MAJOR}.${MIN_MINOR}+ is still not on PATH."
      open_url "https://www.python.org/downloads/"
      exit 1
    fi
  else
    echo "Could not auto-install. Opening https://www.python.org/downloads/"
    open_url "https://www.python.org/downloads/"
    exit 1
  fi
fi

echo "First launch may install packages. The browser opens when ready."
nohup "$PY" run_app.py > herbie.log 2>&1 &

for _ in $(seq 1 180); do
  if curl -sf "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
    open_url "http://127.0.0.1:8000/"
    exit 0
  fi
  sleep 1
done

echo "Server did not become ready in time. Check herbie.log"
exit 1
