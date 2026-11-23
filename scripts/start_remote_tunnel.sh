#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/data/logs"
mkdir -p "$LOG_DIR"
TUNNEL_LOG="$LOG_DIR/cloudflared.log"
URL_FILE="$LOG_DIR/cloudflared-url.txt"
PID_FILE="$LOG_DIR/cloudflared.pid"
FORCE="${1:-}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not installed. Run: bash scripts/install_cloudflared.sh" >&2
  exit 1
fi

if ! curl -sk https://127.0.0.1:8443/api/health >/dev/null; then
  echo "Local server not reachable on 127.0.0.1:8443. Start it first:" >&2
  echo "  cd $ROOT && bash scripts/run_server.sh --tls --host 0.0.0.0" >&2
  exit 1
fi

current_url() {
  if [[ -f "$URL_FILE" ]]; then
    tr -d '\r\n' < "$URL_FILE"
  else
    grep -Eo 'https://[-a-zA-Z0-9]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | tail -n1 || true
  fi
}

is_running() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    return 0
  fi
  pgrep -f "cloudflared tunnel --url https://127.0.0.1:8443" >/dev/null 2>&1
}

if [[ "$FORCE" != "--force" ]] && is_running; then
  URL="$(current_url)"
  if [[ -n "$URL" ]]; then
    if curl -sS --max-time 15 "$URL/api/health" >/dev/null 2>&1; then
      echo "PUBLIC_URL=$URL"
      echo "Dashboard: $URL/"
      echo "Health:    $URL/api/health"
      echo "Tunnel already running. Reusing existing URL (use --force to restart)."
      exit 0
    fi
  fi
fi

pkill -f "cloudflared tunnel --url https://127.0.0.1:8443" >/dev/null 2>&1 || true
pkill -f "cloudflared tunnel --url https://192.168.0.140:8443" >/dev/null 2>&1 || true
sleep 1
: > "$TUNNEL_LOG"

nohup cloudflared tunnel --url https://127.0.0.1:8443 --no-tls-verify --no-autoupdate --protocol http2 >"$TUNNEL_LOG" 2>&1 &
echo $! > "$PID_FILE"

for _ in $(seq 1 60); do
  URL=$(grep -Eo 'https://[-a-zA-Z0-9]+\.trycloudflare\.com' "$TUNNEL_LOG" | tail -n1 || true)
  if [[ -n "$URL" ]]; then
    echo "$URL" > "$URL_FILE"
    if curl -sS --max-time 20 "$URL/api/health" >/dev/null 2>&1; then
      echo "PUBLIC_URL=$URL"
      echo "Dashboard: $URL/"
      echo "Health:    $URL/api/health"
      echo "Log:       $TUNNEL_LOG"
      echo "Use this PUBLIC_URL in the Android app Server URL for remote access."
      exit 0
    fi
  fi
  sleep 1
done

URL=$(current_url)
if [[ -n "$URL" ]]; then
  echo "PUBLIC_URL=$URL"
  echo "Tunnel URL found but health check not confirmed yet. Check: curl -sS $URL/api/health"
  exit 0
fi

echo "Tunnel started but URL not found. Check log: $TUNNEL_LOG" >&2
tail -n 40 "$TUNNEL_LOG" >&2 || true
exit 1
