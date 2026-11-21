#!/usr/bin/env python3
"""Export an encrypted-at-rest SQLite audit history as JSON (operator export)."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export audit history for a device")
    parser.add_argument("--database", required=True)
    parser.add_argument("--device-id", type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    db = sqlite3.connect(args.database)
    db.row_factory = sqlite3.Row
    if args.device_id:
        rows = db.execute(
            "SELECT id, captured_at, received_at, payload FROM telemetry "
            "WHERE device_id = ? ORDER BY id", (args.device_id,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, device_id, captured_at, received_at, payload FROM telemetry ORDER BY id"
        ).fetchall()
    output = [
        {
            **dict(row),
            "payload": json.loads(row["payload"]),
        }
        for row in rows
    ]
    target = Path(args.output)
    target.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Exported {len(output)} reports to {target}")


if __name__ == "__main__":
    main()
