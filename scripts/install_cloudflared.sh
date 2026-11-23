#!/usr/bin/env bash
set -euo pipefail
if command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared already installed: $(command -v cloudflared)"
  cloudflared --version || true
  exit 0
fi
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) PKG="cloudflared-linux-amd64.deb" ;;
  aarch64|arm64) PKG="cloudflared-linux-arm64.deb" ;;
  armv7l|armhf) PKG="cloudflared-linux-armhf.deb" ;;
  *) echo "Unsupported arch: $ARCH" >&2; exit 1 ;;
esac
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
URL="https://github.com/cloudflare/cloudflared/releases/latest/download/$PKG"
echo "Downloading $URL"
curl -fsSL "$URL" -o "$TMP/cloudflared.deb"
dpkg -i "$TMP/cloudflared.deb" || apt-get install -f -y
cloudflared --version
