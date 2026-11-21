"""Telemetry evaluation. Every rule is deterministic and visible to the device owner."""
from __future__ import annotations

import json
from typing import Any

from .util import utcnow

OWN_PACKAGE = "com.darkprime.app"


def _alist(value: Any) -> list:
    return value if isinstance(value, list) else []


def _add(out: list, code: str, severity: str, title: str, subject: str, detail: str) -> None:
    out.append(
        {
            "fingerprint": f"{code}:{subject}"[:240],
            "severity": severity,
            "code": code,
            "title": title,
            "detail": detail[:500],
        }
    )


def evaluate(db, device_id: int, payload: dict, previous: dict | None) -> list[dict]:
    out: list[dict] = []
    device = payload.get("device") if isinstance(payload.get("device"), dict) else {}
    sec = payload.get("security") if isinstance(payload.get("security"), dict) else {}
    battery = payload.get("battery") if isinstance(payload.get("battery"), dict) else {}
    storage = payload.get("storage") if isinstance(payload.get("storage"), dict) else {}
    apps = [a for a in _alist(payload.get("apps")) if isinstance(a, dict)]

    # OS freshness
    sdk = device.get("sdk")
    if isinstance(sdk, int) and sdk < 0:
        sdk = -1
    if isinstance(sdk, int) and sdk < 100:
        from flask import current_app

        minimum = current_app.config["MIN_SUPPORTED_ANDROID_SDK"]
        if sdk < minimum:
            _add(out, "OLD_ANDROID", "medium", "Android version is no longer supported",
                 str(device.get("android_version", "unknown")),
                 f"SDK {sdk} is below the configured minimum of {minimum}.")

    # Accessibility services: only DARKPRIME's own service is expected.
    enabled = [str(x) for x in _alist(sec.get("accessibility_services"))]
    foreign = [x for x in enabled if OWN_PACKAGE not in x]
    if foreign:
        _add(out, "ACCESSIBILITY_SERVICE", "high", "Third-party accessibility service enabled",
             ",".join(sorted(set(foreign))[:4]) or "unknown",
             "Accessibility services can observe on-screen content. Confirm each one is intended: "
             + ", ".join(sorted(set(foreign))[:8]))

    # Device administrators: DARKPRIME's own admin is expected; others are reported.
    admins = [str(x) for x in _alist(sec.get("device_admins"))]
    foreign_admins = [x for x in admins if OWN_PACKAGE not in x]
    if foreign_admins:
        _add(out, "DEVICE_ADMIN", "high", "Additional device administrator active",
             ",".join(sorted(set(foreign_admins))[:4]) or "unknown",
             "Device admins can enforce policy and, in some cases, wipe the device: "
             + ", ".join(sorted(set(foreign_admins))[:8]))

    if sec.get("screen_lock_secure") is False:
        _add(out, "NO_SCREEN_LOCK", "high", "No secure screen lock", "screen_lock",
             "KeyguardManager reports the device is not secured with PIN, pattern, password or biometrics.")

    if sec.get("usb_debugging") is True:
        _add(out, "USB_DEBUGGING", "medium", "USB debugging is enabled", "adb_enabled",
             "ADB is enabled on the device. Keep it off unless actively needed and never expose ADB over a network.")

    if sec.get("unknown_sources") is True:
        _add(out, "UNKNOWN_SOURCES", "medium", "Installation from unknown sources is enabled", "unknown_sources",
             "Apps may be installed outside the verified app store.")

    if isinstance(sec.get("encryption_status"), int) and sec["encryption_status"] in (0, 1):
        _add(out, "NO_ENCRYPTION", "medium", "Device storage is not fully encrypted", "encryption",
             f"Encryption status code: {sec['encryption_status']}.")

    if sec.get("developer_options") is True:
        _add(out, "DEVELOPER_OPTIONS", "low", "Developer options are enabled", "developer_options",
             "Developer options are enabled on this device.")

    level = battery.get("level")
    if isinstance(level, (int, float)) and level <= 15 and battery.get("charging") is False:
        _add(out, "LOW_BATTERY", "info", "Battery is low", "battery",
             f"Battery level is {level}%.")

    free = storage.get("free_percent")
    if isinstance(free, (int, float)) and free < 10:
        _add(out, "LOW_STORAGE", "low", "Free storage is below 10%", "storage",
             f"Free storage is {free}%.")

    # Change detection against the previous snapshot (informational, not accusatory).
    if previous:
        prev_apps = [a for a in _alist(previous.get("apps")) if isinstance(a, dict)]
        prev_by_pkg = {str(a.get("package")): a for a in prev_apps}
        now_by_pkg = {str(a.get("package")): a for a in apps}
        for pkg in sorted(set(now_by_pkg) - set(prev_by_pkg))[:25]:
            if not pkg:
                continue
            label = now_by_pkg[pkg].get("label") or pkg
            _add(out, "APP_INSTALLED", "info", "New application observed", pkg,
                 f"{label} ({pkg}) appeared since the previous snapshot.")
        for pkg in sorted(set(prev_by_pkg) - set(now_by_pkg))[:25]:
            if not pkg:
                continue
            label = prev_by_pkg[pkg].get("label") or pkg
            _add(out, "APP_REMOVED", "info", "Application removed", pkg,
                 f"{label} ({pkg}) is no longer in the snapshot.")
        for pkg, app in now_by_pkg.items():
            if pkg not in prev_by_pkg:
                continue
            old_perms = set(_alist(prev_by_pkg[pkg].get("requested_permissions")))
            new_perms = set(_alist(app.get("requested_permissions")))
            added = sorted(new_perms - old_perms)
            if added:
                _add(out, "PERMISSIONS_CHANGED", "low", "Requested permissions changed", pkg,
                     f"{app.get('label') or pkg} now declares: {', '.join(added[:10])}")

    created = []
    for alert in out:
        cur = db.execute(
            """INSERT OR IGNORE INTO alerts
               (device_id, fingerprint, severity, code, title, detail, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (device_id, alert["fingerprint"], alert["severity"], alert["code"],
             alert["title"], alert["detail"], utcnow()),
        )
        if cur.rowcount:
            row = db.execute("SELECT * FROM alerts WHERE id = ?", (cur.lastrowid,)).fetchone()
            created.append(dict(row))
    db.commit()
    return created


def severity_counts(db, device_id: int) -> dict:
    rows = db.execute(
        "SELECT severity, COUNT(*) AS n FROM alerts WHERE device_id = ? AND acknowledged_at IS NULL GROUP BY severity",
        (device_id,),
    ).fetchall()
    return {r["severity"]: r["n"] for r in rows}


def latest_payload(db, device_id: int) -> dict | None:
    row = db.execute(
        "SELECT payload FROM telemetry WHERE device_id = ? ORDER BY id DESC LIMIT 1", (device_id,)
    ).fetchone()
    if not row:
        return None
    try:
        value = json.loads(row["payload"])
        return value if isinstance(value, dict) else None
    except (ValueError, TypeError):
        return None
