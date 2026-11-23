#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "== local server =="
curl -sk https://127.0.0.1:8443/api/health || true
echo
echo "== tunnel url =="
cat "$ROOT/data/logs/cloudflared-url.txt" 2>/dev/null || grep -Eo 'https://[-a-zA-Z0-9]+\.trycloudflare\.com' "$ROOT/data/logs/cloudflared.log" | tail -n1 || true
echo
echo "== tunnel process =="
ps aux | grep '[c]loudflared tunnel' || true
