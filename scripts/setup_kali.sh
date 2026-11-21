#!/usr/bin/env bash
# Beginner-friendly Kali Linux setup for DARKPRIME.
# Run from anywhere:  bash ~/Desktop/DARKPRIME/scripts/setup_kali.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ $EUID -eq 0 ]]; then SUDO=""; else SUDO="sudo"; fi

echo "[1/7] Installing system packages (requires sudo/root)"
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq python3 python3-venv python3-pip openssl curl ca-certificates nginx

echo "[2/7] Creating Python virtual environment"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r server/requirements.txt

echo "[3/7] Generating secrets"
ENV_FILE="$ROOT/data/darkprime.env"
mkdir -p "$ROOT/data"
if [[ ! -f "$ENV_FILE" ]]; then
  SECRET="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
  PEPPER="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
  cat > "$ENV_FILE" <<EOF
export DARKPRIME_SECRET_KEY="$SECRET"
export DARKPRIME_TOKEN_PEPPER="$PEPPER"
export DARKPRIME_DATA_DIR="$ROOT/data"
export DARKPRIME_DATABASE="$ROOT/data/darkprime.sqlite3"
# Enable these three only after HTTPS is configured with a trusted certificate:
# export DARKPRIME_REQUIRE_HTTPS=1
# export DARKPRIME_COOKIE_SECURE=1
EOF
  chmod 600 "$ENV_FILE"
  echo "Created $ENV_FILE (secrets are never printed)."
fi

echo "[4/7] Generating development TLS certificate"
if [[ ! -f server/certs/server.crt || ! -f server/certs/server.key ]]; then
  SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  SERVER_IP="${SERVER_IP:-127.0.0.1}"
  bash scripts/generate_cert.sh "$ROOT/server/certs" "darkprime.local" "$SERVER_IP"
fi

echo "[5/7] Initializing database"
set -a; source "$ENV_FILE"; set +a
.venv/bin/python -m server.scripts.init_db

echo "[6/7] Creating operator account"
if [[ -z "${DARKPRIME_ADMIN_USER:-}" || -z "${DARKPRIME_ADMIN_PASS:-}" ]]; then
  echo "Choose an operator username and a password of at least 12 characters."
fi
.venv/bin/python -m server.scripts.create_operator

echo "[7/7] Done"
echo "Start with:  $ROOT/scripts/run_server.sh --tls --host 0.0.0.0"
echo "Dashboard:   https://<this-machine-ip>:8443/"
echo "For a public cloud server, use a real domain + Let's Encrypt, nginx and gunicorn (see docs/INSTALL_KALI.md)."
echo "Do NOT forward port 8443 through the public internet for local testing; do NOT expose ADB."
