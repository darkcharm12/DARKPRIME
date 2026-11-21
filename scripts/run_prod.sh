#!/usr/bin/env bash
# Run the production WSGI app with gunicorn behind nginx.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f data/darkprime.env ]]; then
  set -a; source data/darkprime.env; set +a
fi

export DARKPRIME_REQUIRE_HTTPS="${DARKPRIME_REQUIRE_HTTPS:-1}"
export DARKPRIME_COOKIE_SECURE="${DARKPRIME_COOKIE_SECURE:-1}"

exec "$ROOT/.venv/bin/gunicorn" \
  --bind 127.0.0.1:8000 \
  --workers "${DARKPRIME_WORKERS:-2}" \
  --timeout 60 \
  --access-logfile - \
  --error-logfile - \
  "server.app:create_app()"
