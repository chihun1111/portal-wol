#!/usr/bin/env bash
set -euo pipefail

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

APP_DIR="/srv/wol-core"
HOST="0.0.0.0"
PORT="${WOL_WEB_PORT:-8000}"
LOG_DIR="$APP_DIR/logs"
WATCHDOG_LOG="$LOG_DIR/wol-web-watchdog.log"
PID_FILE="$LOG_DIR/wol-web-watchdog.pid"
LOCK_FILE="/tmp/wol-web-watchdog.lock"

mkdir -p "$LOG_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  exit 0
fi

log() {
  printf '%s %s\n' "$(date -Is)" "$*" >> "$WATCHDOG_LOG"
}

# Avoid racing the native systemd unit during early boot.
uptime_seconds="$(cut -d. -f1 /proc/uptime)"
if [[ "$uptime_seconds" =~ ^[0-9]+$ ]] && (( uptime_seconds < 90 )); then
  exit 0
fi

is_port_listening() {
  ss -ltn "sport = :$PORT" | grep -q LISTEN
}

if is_port_listening; then
  exit 0
fi

unit_state="$(systemctl is-active wol-web 2>/dev/null || true)"
if [[ "$unit_state" == "activating" || "$unit_state" == "reloading" ]]; then
  exit 0
fi

# Prefer the registered systemd unit when policy allows it; fall back to a direct uvicorn process otherwise.
if systemctl --no-ask-password start wol-web >/dev/null 2>&1; then
  sleep 2
  if is_port_listening; then
    log "started wol-web via systemd"
    exit 0
  fi
fi

cd "$APP_DIR"
if [[ ! -x "$APP_DIR/.venv/bin/uvicorn" ]]; then
  log "uvicorn not found at $APP_DIR/.venv/bin/uvicorn"
  exit 1
fi

nohup "$APP_DIR/.venv/bin/uvicorn" app.main:create_app --factory --host "$HOST" --port "$PORT" >> "$WATCHDOG_LOG" 2>&1 &
pid="$!"
printf '%s\n' "$pid" > "$PID_FILE"
log "started fallback uvicorn pid=$pid on $HOST:$PORT"
