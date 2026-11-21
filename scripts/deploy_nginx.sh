#!/usr/bin/env bash
# Install the nginx reverse proxy that terminates TLS in front of gunicorn.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${1:-darkprime.local}"
if [[ $EUID -eq 0 ]]; then SUDO=""; else SUDO="sudo"; fi

$SUDO apt-get install -y -qq nginx
$SUDO mkdir -p /etc/darkprime/certs /etc/darkprime/logs
$SUDO cp "$ROOT/server/certs/server.crt" /etc/darkprime/certs/server.crt
$SUDO cp "$ROOT/server/certs/server.key" /etc/darkprime/certs/server.key
$SUDO chmod 600 /etc/darkprime/certs/server.key

sed "s/DARKPRIME_SERVER_NAME/$DOMAIN/g" "$ROOT/nginx/darkprime.conf" > /tmp/darkprime-nginx.conf
$SUDO cp /tmp/darkprime-nginx.conf /etc/nginx/sites-available/darkprime
$SUDO ln -sf /etc/nginx/sites-available/darkprime /etc/nginx/sites-enabled/darkprime
$SUDO nginx -t
$SUDO systemctl restart nginx
echo "nginx configured for https://$DOMAIN/ -> 127.0.0.1:8000"
