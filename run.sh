#!/usr/bin/env bash
# Self-contained launcher for the portable Voyage PDF Search demo.
#
# The first run installs a pinned standalone Python under vendor/, creates a
# private virtual environment, and installs the pinned application packages.
# Later runs reuse those local assets. No system Python installation is needed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-8020}"
HOST="127.0.0.1"
APP_URL="http://${HOST}:${PORT}/"
VENDOR_DIR="$SCRIPT_DIR/vendor"
PYTHON_BIN="$VENDOR_DIR/python/install/bin/python3"
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"
VENV_RUNTIME_STAMP="$VENV_DIR/.portable-python-version"
REQ_FILE="$SCRIPT_DIR/requirements.lock"
REQ_STAMP="$VENV_DIR/.requirements.sha256"
RUNTIME_DIR="$SCRIPT_DIR/.runtime"
APP_PID_FILE="$RUNTIME_DIR/app-${PORT}.pid"
APP_PID=""
BROWSER_WAITER_PID=""

case "$PORT" in
  ''|*[!0-9]*) echo "ERROR: PORT must be a number." >&2; exit 1 ;;
esac
if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  echo "ERROR: PORT must be between 1 and 65535." >&2
  exit 1
fi

process_cwd() {
  local pid="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
  elif [ -e "/proc/$pid/cwd" ] && command -v readlink >/dev/null 2>&1; then
    readlink -f "/proc/$pid/cwd" 2>/dev/null || true
  fi
}

process_is_this_demo() {
  local pid="$1" command cwd
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  cwd="$(process_cwd "$pid")"
  [ "$cwd" = "$SCRIPT_DIR" ] && [[ "$command" == *"app.main:app"* ]]
}

is_descendant_of() {
  local pid="$1" ancestor="$2" parent
  while [ -n "$pid" ] && [ "$pid" -gt 1 ] 2>/dev/null; do
    [ "$pid" = "$ancestor" ] && return 0
    parent="$(ps -p "$pid" -o ppid= 2>/dev/null | tr -d ' ' || true)"
    [ -n "$parent" ] && [ "$parent" != "$pid" ] || break
    pid="$parent"
  done
  return 1
}

listener_pids() {
  lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | sort -u || true
}

port_is_listening() {
  (exec 3<>"/dev/tcp/${HOST}/${PORT}") >/dev/null 2>&1
}

stop_demo_pid() {
  local pid="$1"
  echo "Port $PORT is already used by this demo (pid $pid); restarting it ..."
  pkill -TERM -P "$pid" 2>/dev/null || true
  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 40); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    pkill -KILL -P "$pid" 2>/dev/null || true
    kill -KILL "$pid" 2>/dev/null || true
  fi
}

handoff_port() {
  local owners="" stored_pid="" stored_launcher="" owner matched=0 demo_pid=""
  local launcher_command=""

  mkdir -p "$RUNTIME_DIR"
  if command -v lsof >/dev/null 2>&1; then
    owners="$(listener_pids)"
    if [ -z "$owners" ]; then
      rm -f "$APP_PID_FILE"
      return 0
    fi
    if [ -f "$APP_PID_FILE" ]; then
      read -r stored_pid stored_launcher < "$APP_PID_FILE" || true
    fi
    if [ -n "$stored_pid" ] && kill -0 "$stored_pid" 2>/dev/null; then
      matched=1
      for owner in $owners; do
        if ! is_descendant_of "$owner" "$stored_pid"; then
          matched=0
          break
        fi
      done
      [ "$matched" -eq 1 ] && demo_pid="$stored_pid"
    fi
    if [ -z "$demo_pid" ]; then
      matched=1
      for owner in $owners; do
        if ! process_is_this_demo "$owner"; then
          matched=0
          break
        fi
      done
      [ "$matched" -eq 1 ] && demo_pid="$(printf '%s\n' "$owners" | head -n 1)"
    fi
  else
    if ! port_is_listening; then
      rm -f "$APP_PID_FILE"
      return 0
    fi
    if [ -f "$APP_PID_FILE" ]; then
      read -r stored_pid stored_launcher < "$APP_PID_FILE" || true
    fi
    if [ -n "$stored_pid" ] && kill -0 "$stored_pid" 2>/dev/null && process_is_this_demo "$stored_pid"; then
      demo_pid="$stored_pid"
    fi
  fi

  if [ -z "$demo_pid" ]; then
    echo "ERROR: port $PORT belongs to another application and was not stopped." >&2
    echo "Choose another port, for example: PORT=8030 ./run.sh" >&2
    exit 1
  fi

  stop_demo_pid "$demo_pid"
  if [ -n "$stored_launcher" ]; then
    launcher_command="$(ps -p "$stored_launcher" -o command= 2>/dev/null || true)"
    if [[ "$launcher_command" == *"run.sh"* ]]; then
      for _ in $(seq 1 80); do
        kill -0 "$stored_launcher" 2>/dev/null || break
        sleep 0.25
      done
    fi
  fi
  rm -f "$APP_PID_FILE"

  for _ in $(seq 1 40); do
    if command -v lsof >/dev/null 2>&1; then
      [ -z "$(listener_pids)" ] && return 0
    elif ! port_is_listening; then
      return 0
    fi
    sleep 0.25
  done
  echo "ERROR: the previous demo did not release port $PORT." >&2
  exit 1
}

file_sha256() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    "$PYTHON_BIN" -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$1"
  fi
}

cleanup() {
  if [ -n "$BROWSER_WAITER_PID" ]; then
    kill "$BROWSER_WAITER_PID" 2>/dev/null || true
  fi
  if [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
    kill -TERM "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
  fi
  if [ -n "$APP_PID" ] && [ -f "$APP_PID_FILE" ]; then
    local file_pid=""
    read -r file_pid _ < "$APP_PID_FILE" || true
    [ "$file_pid" = "$APP_PID" ] && rm -f "$APP_PID_FILE"
  fi
}
trap cleanup EXIT

open_browser_when_ready() {
  for _ in $(seq 1 180); do
    kill -0 "$APP_PID" 2>/dev/null || return 0
    if "$VENV_PY" -c 'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=1).read(1)' "$APP_URL" >/dev/null 2>&1; then
      if command -v open >/dev/null 2>&1; then
        open "$APP_URL" >/dev/null 2>&1 || true
      elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$APP_URL" >/dev/null 2>&1 || true
      fi
      return 0
    fi
    sleep 0.5
  done
  echo "The browser did not open automatically. Visit $APP_URL" >&2
}

printf '\n============================================================\n'
printf '  Voyage PDF Search Portable Demo\n'
printf '  URL: %s\n' "$APP_URL"
printf '============================================================\n\n'

echo "Ensuring the bundled Python runtime is installed ..."
bash "$SCRIPT_DIR/scripts/setup-python.sh"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "ERROR: bundled Python was not installed at $PYTHON_BIN." >&2
  exit 1
fi

portable_python_version="$("$PYTHON_BIN" -c 'import platform; print(platform.python_version())')"
venv_python_version="$(cat "$VENV_RUNTIME_STAMP" 2>/dev/null || true)"
if [ -d "$VENV_DIR" ] && [ "$venv_python_version" != "$portable_python_version" ]; then
  echo "Replacing an environment that was not built with bundled Python $portable_python_version ..."
  rm -rf "$VENV_DIR"
fi
if [ -d "$VENV_DIR" ] && [ ! -x "$VENV_PY" ]; then
  echo "Replacing a broken or relocated private Python environment ..."
  rm -rf "$VENV_DIR"
fi
if [ ! -x "$VENV_PY" ]; then
  echo "Creating the private Python environment ..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  printf '%s\n' "$portable_python_version" > "$VENV_RUNTIME_STAMP"
fi

if [ ! -f "$REQ_FILE" ]; then
  echo "ERROR: hash-locked dependency manifest is missing: $REQ_FILE" >&2
  exit 1
fi

requirements_hash="$(file_sha256 "$REQ_FILE")"
installed_hash="$(cat "$REQ_STAMP" 2>/dev/null || true)"
if [ "$requirements_hash" != "$installed_hash" ]; then
  echo "Installing hash-verified application dependencies ..."
  "$VENV_PY" -m pip install --disable-pip-version-check --require-hashes -r "$REQ_FILE"
  printf '%s\n' "$requirements_hash" > "$REQ_STAMP"
else
  echo "Application dependencies are already up to date."
fi

# Delay port handoff until runtime setup has succeeded so an existing demo is
# not interrupted by a failed download or dependency installation.
handoff_port

echo
echo "Starting Voyage PDF Search at $APP_URL"
echo "Press Ctrl+C to stop. Re-run ./run.sh to restart."
echo

PYTHONPATH=. "$VENV_PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT" &
APP_PID=$!
printf '%s %s\n' "$APP_PID" "$$" > "$APP_PID_FILE"
if [ "${NO_BROWSER:-0}" != "1" ]; then
  open_browser_when_ready &
  BROWSER_WAITER_PID=$!
fi

forward_signal() {
  pkill -TERM -P "$APP_PID" 2>/dev/null || true
  kill -TERM "$APP_PID" 2>/dev/null || true
}
trap forward_signal INT TERM

APP_EXIT=0
wait "$APP_PID" || APP_EXIT=$?
wait "$APP_PID" 2>/dev/null || true
trap - INT TERM
exit "$APP_EXIT"
