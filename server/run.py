#!/usr/bin/env python3
"""Development runner with optional local TLS. Production uses nginx + gunicorn."""
from __future__ import annotations

import argparse
from pathlib import Path

from server.app import create_app
from server.config import TLS_CERT, TLS_KEY
from server.db import init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DARKPRIME server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--tls", action="store_true", help="use the generated self-signed certificate")
    args = parser.parse_args()

    app = create_app()
    init_db(app.config["DATABASE"])
    ssl_context = None
    if args.tls:
        if not TLS_CERT.exists() or not TLS_KEY.exists():
            raise SystemExit("TLS files missing. Run scripts/generate_cert.sh first.")
        ssl_context = (str(TLS_CERT), str(TLS_KEY))
    app.run(host=args.host, port=args.port, ssl_context=ssl_context, threaded=True)


if __name__ == "__main__":
    main()
