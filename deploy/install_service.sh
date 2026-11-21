#!/usr/bin/env bash
# Install the gunicorn systemd service. Run after scripts/setup_kali.sh and nginx setup.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-/opt/darkprime}"
if [[ $EUID -eq 0 ]]; then SUDO=""; else SUDO="sudo"; fi

$SUDO mkdir -p "$TARGET"
$SUDO cp -a "$ROOT/." "$TARGET/"
if ! id darkprime >/dev/null 2>&1; then $SUDO useradd --system --home-dir "$TARGET" --shell /usr/sbin/nologin darkprime; fi
$SUDO chown -R darkprime:darkprime "$TARGET/data"
$SUDO chmod 700 "$TARGET/data"

$SUDO sed "s|/opt/darkprime|$TARGET|g" "$ROOT/deploy/darkprime.service" > /tmp/darkprime.service
$SUDO cp /tmp/darkprime.service /etc/systemd/system/darkprime.service
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now darkprime
echo "Service installed. Check with: systemctl status darkprime"
