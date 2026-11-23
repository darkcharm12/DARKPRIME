#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/data/logs"
mkdir -p "$LOG_DIR"
TUNNEL_LOG="$LOG_DIR/cloudflared.log"
URL_FILE="$LOG_DIR/cloudflared-url.txt"
: > "$TUNNEL_LOG"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not installed. Run: bash scripts/install_cloudflared.sh" >&2
  exit 1
fi

if ! curl -sk https://192.168.0.140:8443/api/health >/dev/null; then
  echo "Local server not reachable on :8443. Start it first:" >&2
  echo "  bash scripts/run_server.sh --tls --host 0.0.0.0" >&2
  exit 1
fi

pkill -f "cloudflared tunnel --url https://127.0.0.1:8443" >/dev/null 2>&1 || true
pkill -f "cloudflared tunnel --url https://192.168.0.140:8443" >/dev/null 2>&1 || true
nohup cloudflared tunnel --url https://192.168.0.140:8443 --no-tls-verify --no-autoupdate >"$TUNNEL_LOG" 2>&1 &
echo $! > "$LOG_DIR/cloudflared.pid"

for _ in $(seq 1 60); do
  URL=$(grep -Eo 'https://[-a-zA-Z0-9]+\.trycloudflare\.com' "$TUNNEL_LOG" | tail -n1 || true)
  if [[ -n "$URL" ]]; then
    echo "$URL" > "$URL_FILE"
    echo "PUBLIC_URL=$URL"
    echo "Dashboard: $URL/"
    echo "Health:    $URL/api/health"
    echo "Log:       $TUNNEL_LOG"
    echo "Use this PUBLIC_URL in the Android app Server URL for remote access."
    exit 0
  fi
  sleep 1
done

echo "Tunnel started but URL not found yet. Check log: $TUNNEL_LOG" >&2
tail -n 40 "$TUNNEL_LOG" >&2 || true
exit 1
