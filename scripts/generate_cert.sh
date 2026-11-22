#!/usr/bin/env bash
# Generate a self-signed development certificate with SANs for local hostnames/IPs.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${1:-$HERE/../server/certs}"
HOSTNAME_VALUE="${2:-darkprime.local}"
IP_VALUE="${3:-}"

detect_ip() {
  hostname -I 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i ~ /^[0-9.]+$/ && $i !~ /^127\./) {print $i; exit}}' || true
}

if [[ -z "$IP_VALUE" ]]; then
  IP_VALUE="$(detect_ip)"
fi

mkdir -p "$CERT_DIR"
CERT="$CERT_DIR/server.crt"
KEY="$CERT_DIR/server.key"
CONF="$(mktemp)"

trap 'rm -f "$CONF"' EXIT
{
  cat <<EOF
[req]
distinguished_name = dn
x509_extensions = v3_req
prompt = no
[dn]
CN = $HOSTNAME_VALUE
O = DARKPRIME
[v3_req]
subjectAltName = @alt_names
basicConstraints = critical,CA:TRUE
keyUsage = critical,digitalSignature,keyEncipherment,keyCertSign
extendedKeyUsage = serverAuth
[alt_names]
DNS.1 = $HOSTNAME_VALUE
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF
  idx=2
  if [[ -n "$IP_VALUE" && "$IP_VALUE" != "127.0.0.1" ]]; then
    printf 'IP.%s = %s\n' "$idx" "$IP_VALUE"
  fi
} > "$CONF"

openssl req -x509 -newkey rsa:3072 -nodes -days 365 \
  -keyout "$KEY" -out "$CERT" -config "$CONF" >/dev/null 2>&1
chmod 600 "$KEY"
chmod 644 "$CERT"
mkdir -p "$HERE/../android/app/src/main/res/raw"
cp "$CERT" "$HERE/../android/app/src/main/res/raw/darkprime_lab_ca"
printf 'Certificate: %s\nKey: %s\n' "$CERT" "$KEY"
printf 'Certificate copied to the Android app resources. Rebuild the debug APK after regenerating.\n'
