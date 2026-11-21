#!/usr/bin/env python3
"""Create or upgrade the SQLite schema. Safe to run repeatedly."""
from __future__ import annotations

import argparse

from server.app import create_app
from server.db import init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the DARKPRIME database")
    parser.add_argument("--database", help="override the database path")
    args = parser.parse_args()

    app = create_app()
    target = args.database or app.config["DATABASE"]
    init_db(target)
    print(f"Database ready: {target}")


if __name__ == "__main__":
    main()
