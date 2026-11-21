"""SQLite access layer for DARKPRIME."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        path = Path(current_app.config["DATABASE"])
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(path), timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        g.db = db
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(database_path: str | None = None) -> None:
    path = Path(database_path or current_app.config["DATABASE"])
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    db = sqlite3.connect(str(path))
    try:
        db.executescript(schema)
        db.commit()
    finally:
        db.close()


def audit(db: sqlite3.Connection, action: str, *, operator_id=None, device_id=None, detail="") -> None:
    from .util import utcnow

    db.execute(
        "INSERT INTO audit_log (operator_id, device_id, action, detail, created_at) VALUES (?,?,?,?,?)",
        (operator_id, device_id, action, detail, utcnow()),
    )
