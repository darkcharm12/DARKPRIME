#!/usr/bin/env bash
# Generate a self-signed development certificate with a SAN for IP/DNS.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${1:-$HERE/../server/certs}"
HOSTNAME_VALUE="${2:-darkprime.local}"
IP_VALUE="${3:-127.0.0.1}"

mkdir -p "$CERT_DIR"
CERT="$CERT_DIR/server.crt"
KEY="$CERT_DIR/server.key"
CONF="$(mktemp)"

trap 'rm -f "$CONF"' EXIT
cat > "$CONF" <<EOF
[req]
distinguished_name = dn
x509_extensions = v3_req
prompt = no
[dn]
CN = $HOSTNAME_VALUE
O = DARKPRIME
[v3_req]
subjectAltName = @alt_names
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
[alt_names]
DNS.1 = $HOSTNAME_VALUE
DNS.2 = localhost
IP.1 = $IP_VALUE
EOF

openssl req -x509 -newkey rsa:3072 -nodes -days 365 \
  -keyout "$KEY" -out "$CERT" -config "$CONF" >/dev/null 2>&1
chmod 600 "$KEY"
chmod 644 "$CERT"
printf 'Certificate: %s\nKey: %s\n' "$CERT" "$KEY"
printf 'Install server.crt on the Android device (Settings > Security > Install from storage) for local testing.\n'
