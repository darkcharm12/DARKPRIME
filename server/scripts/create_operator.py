#!/usr/bin/env python3
"""Create an operator account from CLI arguments, environment, or a prompt."""
from __future__ import annotations

import argparse
import getpass
import os

from server.app import create_app
from server.auth import create_operator, find_operator
from server.db import get_db, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a DARKPRIME operator account")
    parser.add_argument("--username", default=os.environ.get("DARKPRIME_ADMIN_USER"))
    parser.add_argument("--password", default=os.environ.get("DARKPRIME_ADMIN_PASS"))
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        init_db(app.config["DATABASE"])
        username = args.username or input("Operator username: ").strip()
        password = args.password or getpass.getpass("Operator password (12+ characters): ")
        if find_operator(username):
            raise SystemExit("That operator already exists.")
        try:
            operator_id = create_operator(username, password)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        db = get_db()
        db.commit()
        print(f"Operator created: {username} (id={operator_id})")


if __name__ == "__main__":
    main()
