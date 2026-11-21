#!/usr/bin/env bash
# Run the Flask development server with project secrets and optional TLS.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f data/darkprime.env ]]; then
  set -a; source data/darkprime.env; set +a
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Virtual environment missing. Run scripts/setup_kali.sh first." >&2
  exit 1
fi

exec .venv/bin/python -m server.run "$@"
