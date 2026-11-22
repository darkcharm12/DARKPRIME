"""HTTPS REST API used by the Android companion app and by the Kali-side dashboard tooling."""
from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, request, send_file

from .alerts import evaluate, latest_payload
from .auth import (
    LOGIN_WINDOW_SECONDS,
    check_operator_login,
    clear_login_failures,
    create_operator_session,
    login_allowed,
    record_login_failure,
    require_device,
    require_operator,
    revoke_operator_session,
)
from .db import audit, get_db
from .util import add_hours, client_ip, hash_token, new_token, parse_time, utcnow

bp = Blueprint("api", __name__)


def error(message: str, status: int, **extra):
    payload = {"error": message}
    payload.update(extra)
    return jsonify(payload), status


def _device_public(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "model": row["model"],
        "android_version": row["android_version"],
        "status": row["status"],
        "consent_at": row["consent_at"],
        "enrolled_at": row["enrolled_at"],
        "last_seen_at": row["last_seen_at"],
        "unenroll_requested_at": row["unenroll_requested_at"],
    }


def _pending_actions(row) -> list[str]:
    actions = []
    if row["unenroll_requested_at"] and row["status"] == "active":
        actions.append("unenroll")
    pending = get_db().execute(
        "SELECT 1 FROM screen_sessions WHERE device_id = ? AND status = 'pending' LIMIT 1",
        (row["id"],),
    ).fetchone()
    if pending:
        actions.append("screen_session")
    return actions


def _poll_seconds() -> int:
    return int(current_app.config["POLL_INTERVAL_SECONDS"])


def _frame_path(session_id: int) -> Path:
    directory = Path(current_app.config["SCREEN_FRAME_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"session-{session_id}.jpg"


def _screen_session_public(row) -> dict:
    return {
        "id": row["id"],
        "device_id": row["device_id"],
        "status": row["status"],
        "requested_at": row["requested_at"],
        "approved_at": row["approved_at"],
        "connected_at": row["connected_at"],
        "last_seen_at": row["last_seen_at"],
        "last_frame_at": row["last_frame_at"],
        "stop_requested_at": row["stop_requested_at"],
        "stopped_at": row["stopped_at"],
        "has_frame": bool(row["frame_path"]),
    }


def _operator_session(db, session_id: int, operator_id: int):
    return db.execute(
        """SELECT s.* FROM screen_sessions s
           JOIN devices d ON d.id = s.device_id
           WHERE s.id = ? AND d.operator_id = ?""",
        (session_id, operator_id),
    ).fetchone()


def _device_session(db, session_id: int, device_id: int):
    return db.execute(
        "SELECT * FROM screen_sessions WHERE id = ? AND device_id = ?",
        (session_id, device_id),
    ).fetchone()


@bp.get("/api/health")
def health():
    return jsonify(ok=True, service="DARKPRIME", time=utcnow())


@bp.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    ip = client_ip()
    if not login_allowed(ip):
        return error("too_many_attempts", 429, retry_after_seconds=LOGIN_WINDOW_SECONDS)
    op = check_operator_login(str(data.get("username", "")), str(data.get("password", "")))
    if not op:
        record_login_failure(ip)
        audit(get_db(), "operator.login.failed", detail=f"username={data.get('username', '')} ip={ip}")
        get_db().commit()
        return error("invalid_credentials", 401)
    clear_login_failures(ip)
    token = create_operator_session(op["id"])
    audit(get_db(), "operator.login", operator_id=op["id"], detail=f"ip={client_ip()}")
    get_db().commit()
    return jsonify(token=token, operator={"id": op["id"], "username": op["username"]})


@bp.post("/api/auth/logout")
def logout():
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        revoke_operator_session(header[7:].strip())
        return jsonify(ok=True)
    return error("bearer_token_required", 400)


@bp.post("/api/enrollment-tokens")
@require_operator
def create_enrollment_token():
    data = request.get_json(silent=True) or {}
    label = str(data.get("label", ""))[:120]
    raw = new_token(24)
    db = get_db()
    db.execute(
        """INSERT INTO enrollment_tokens
           (operator_id, token_hash, label, created_at, expires_at) VALUES (?,?,?,?,?)""",
        (g.operator["id"], hash_token(raw), label, utcnow(),
         add_hours(int(current_app.config["ENROLLMENT_TOKEN_TTL_HOURS"]))),
    )
    audit(db, "enrollment_token.created", operator_id=g.operator["id"], detail=label)
    db.commit()
    return jsonify(token=raw, expires_in_hours=current_app.config["ENROLLMENT_TOKEN_TTL_HOURS"]), 201


@bp.get("/api/enrollment-tokens")
@require_operator
def list_enrollment_tokens():
    rows = get_db().execute(
        """SELECT id, label, created_at, expires_at, used_at, device_id
           FROM enrollment_tokens WHERE operator_id = ? ORDER BY id DESC LIMIT 100""",
        (g.operator["id"],),
    ).fetchall()
    return jsonify(items=[dict(r) for r in rows])


@bp.post("/api/devices/enroll")
def enroll_device():
    data = request.get_json(silent=True) or {}
    raw_token = str(data.get("enrollment_token", ""))
    uuid = str(data.get("device_uuid", "")).strip()
    consent = data.get("consent") if isinstance(data.get("consent"), dict) else {}
    if not uuid or len(uuid) > 128:
        return error("invalid_device_uuid", 400)
    if consent.get("accepted") is not True:
        return error("explicit_consent_required", 403)
    db = get_db()
    token_row = db.execute(
        "SELECT * FROM enrollment_tokens WHERE token_hash = ?", (hash_token(raw_token),)
    ).fetchone()
    if not token_row:
        return error("invalid_enrollment_token", 401)
    if token_row["used_at"]:
        return error("enrollment_token_already_used", 409)
    if parse_time(token_row["expires_at"]) <= parse_time(utcnow()):
        return error("enrollment_token_expired", 410)
    if db.execute("SELECT 1 FROM devices WHERE device_uuid = ?", (uuid,)).fetchone():
        return error("device_already_enrolled", 409)

    device_token = new_token(32)
    now = utcnow()
    cur = db.execute(
        """INSERT INTO devices
           (operator_id, device_uuid, name, model, android_version, token_hash, consent_at, enrolled_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            token_row["operator_id"], uuid,
            str(data.get("name") or "Android device")[:120],
            str(data.get("model") or "")[:120],
            str(data.get("android_version") or "")[:80],
            hash_token(device_token), str(consent.get("at") or now)[:40], now,
        ),
    )
    device_id = cur.lastrowid
    db.execute(
        "UPDATE enrollment_tokens SET used_at = ?, device_id = ? WHERE id = ?",
        (now, device_id, token_row["id"]),
    )
    audit(db, "device.enrolled", operator_id=token_row["operator_id"], device_id=device_id,
          detail=f"uuid={uuid} model={data.get('model', '')}")
    db.commit()
    return jsonify(
        device_id=device_id,
        token=device_token,
        poll_interval_seconds=_poll_seconds(),
        monitoring_disclosure="This device is actively monitored. Monitoring is visible in the app and can be stopped at any time.",
    ), 201


@bp.get("/api/devices")
@require_operator
def list_devices():
    rows = get_db().execute(
        """SELECT d.*,
                  (SELECT COUNT(*) FROM alerts a WHERE a.device_id = d.id AND a.acknowledged_at IS NULL) AS open_alerts
           FROM devices d WHERE d.operator_id = ? ORDER BY d.id DESC""",
        (g.operator["id"],),
    ).fetchall()
    items = []
    for r in rows:
        item = _device_public(r)
        item["open_alerts"] = r["open_alerts"]
        items.append(item)
    return jsonify(items=items)


@bp.get("/api/devices/<int:device_id>")
@require_operator
def get_device(device_id: int):
    row = get_db().execute(
        "SELECT * FROM devices WHERE id = ? AND operator_id = ?", (device_id, g.operator["id"])
    ).fetchone()
    if not row:
        return error("device_not_found", 404)
    item = _device_public(row)
    item["latest"] = latest_payload(get_db(), device_id)
    return jsonify(device=item)


@bp.get("/api/devices/<int:device_id>/history")
@require_operator
def device_history(device_id: int):
    db = get_db()
    if not db.execute("SELECT 1 FROM devices WHERE id = ? AND operator_id = ?",
                      (device_id, g.operator["id"])).fetchone():
        return error("device_not_found", 404)
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 500)
    except (TypeError, ValueError):
        limit = 50
    rows = db.execute(
        "SELECT id, captured_at, received_at, payload FROM telemetry WHERE device_id = ? ORDER BY id DESC LIMIT ?",
        (device_id, limit),
    ).fetchall()
    return jsonify(items=[{"id": r["id"], "captured_at": r["captured_at"],
                           "received_at": r["received_at"],
                           "payload": json.loads(r["payload"])} for r in rows])


@bp.get("/api/devices/<int:device_id>/alerts")
@require_operator
def device_alerts(device_id: int):
    db = get_db()
    if not db.execute("SELECT 1 FROM devices WHERE id = ? AND operator_id = ?",
                      (device_id, g.operator["id"])).fetchone():
        return error("device_not_found", 404)
    rows = db.execute(
        "SELECT * FROM alerts WHERE device_id = ? ORDER BY (acknowledged_at IS NULL) DESC, id DESC LIMIT 500",
        (device_id,),
    ).fetchall()
    return jsonify(items=[dict(r) for r in rows])


@bp.post("/api/devices/<int:device_id>/unenroll")
@require_operator
def request_unenroll(device_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM devices WHERE id = ? AND operator_id = ?",
                     (device_id, g.operator["id"])).fetchone()
    if not row:
        return error("device_not_found", 404)
    if row["status"] != "active":
        return error("device_not_active", 409)
    db.execute("UPDATE devices SET unenroll_requested_at = ? WHERE id = ?", (utcnow(), device_id))
    audit(db, "device.unenroll_requested", operator_id=g.operator["id"], device_id=device_id)
    db.commit()
    return jsonify(ok=True, pending_actions=["unenroll"])


@bp.get("/api/devices/me")
@require_device
def my_device():
    d = g.device
    return jsonify(
        device_id=d["id"], name=d["name"], status=d["status"],
        enrolled_at=d["enrolled_at"], last_seen_at=d["last_seen_at"],
        pending_actions=_pending_actions(d), poll_interval_seconds=_poll_seconds(),
    )


@bp.post("/api/devices/me/telemetry")
@require_device
def post_telemetry():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("invalid_json", 400)
    if not isinstance(data.get("device"), dict) or not isinstance(data.get("security"), dict):
        return error("missing_required_sections", 400)
    db = get_db()
    device_id = g.device["id"]
    last = parse_time(g.device["last_seen_at"])
    now_dt = parse_time(utcnow())
    minimum = int(current_app.config["MIN_TELEMETRY_INTERVAL_SECONDS"])
    if last and (now_dt - last).total_seconds() < minimum:
        return error("rate_limited", 429, retry_after_seconds=minimum)

    previous = latest_payload(db, device_id)
    db.execute(
        "INSERT INTO telemetry (device_id, captured_at, received_at, payload) VALUES (?,?,?,?)",
        (device_id, str(data.get("captured_at") or "")[:40], utcnow(),
         json.dumps(data, separators=(",", ":"))),
    )
    db.execute(
        """UPDATE devices SET last_seen_at = ?, last_captured_at = ?, model = ?, android_version = ?
           WHERE id = ?""",
        (utcnow(), str(data.get("captured_at") or "")[:40],
         str(data["device"].get("model") or g.device["model"])[:120],
         str(data["device"].get("android_version") or g.device["android_version"])[:80],
         device_id),
    )
    created = evaluate(db, device_id, data, previous)
    db.commit()
    current = db.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return jsonify(ok=True, alerts_created=len(created),
                   pending_actions=_pending_actions(current),
                   poll_interval_seconds=_poll_seconds())


@bp.post("/api/devices/me/unenroll/request")
@require_device
def device_request_unenroll():
    db = get_db()
    db.execute("UPDATE devices SET unenroll_requested_at = ? WHERE id = ? AND status = 'active'",
               (utcnow(), g.device["id"]))
    audit(db, "device.unenroll_requested_by_owner", device_id=g.device["id"])
    db.commit()
    return jsonify(ok=True, message="Enrollment will be revoked locally and on the server.")


@bp.post("/api/devices/me/unenroll/confirm")
@require_device
def device_confirm_unenroll():
    db = get_db()
    db.execute(
        """UPDATE devices SET status = 'unenrolled', token_hash = NULL, unenrolled_at = ?
           WHERE id = ? AND status = 'active'""",
        (utcnow(), g.device["id"]),
    )
    audit(db, "device.unenrolled", device_id=g.device["id"], detail="owner confirmed")
    db.commit()
    return jsonify(ok=True)


@bp.post("/api/devices/<int:device_id>/screen-sessions")
@require_operator
def request_screen_session(device_id: int):
    db = get_db()
    device = db.execute(
        "SELECT * FROM devices WHERE id = ? AND operator_id = ? AND status = 'active'",
        (device_id, g.operator["id"]),
    ).fetchone()
    if not device:
        return error("device_not_found_or_inactive", 404)
    now = utcnow()
    previous = db.execute(
        """SELECT id, frame_path FROM screen_sessions
           WHERE device_id = ? AND status IN ('pending', 'active', 'stopping')""",
        (device_id,),
    ).fetchall()
    for row in previous:
        if row["frame_path"]:
            Path(row["frame_path"]).unlink(missing_ok=True)
    db.execute(
        """UPDATE screen_sessions SET status = 'expired', stopped_at = ?
           WHERE device_id = ? AND status IN ('pending', 'active', 'stopping')""",
        (now, device_id),
    )
    cur = db.execute(
        """INSERT INTO screen_sessions (device_id, operator_id, status, requested_at)
           VALUES (?,?, 'pending', ?)""",
        (device_id, g.operator["id"], now),
    )
    audit(db, "screen_session.requested", operator_id=g.operator["id"], device_id=device_id,
          detail=f"session={cur.lastrowid}")
    db.commit()
    row = db.execute("SELECT * FROM screen_sessions WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(_screen_session_public(row)), 201


@bp.get("/api/devices/<int:device_id>/screen-sessions")
@require_operator
def list_screen_sessions(device_id: int):
    db = get_db()
    device = db.execute(
        "SELECT 1 FROM devices WHERE id = ? AND operator_id = ?",
        (device_id, g.operator["id"]),
    ).fetchone()
    if not device:
        return error("device_not_found", 404)
    rows = db.execute(
        "SELECT * FROM screen_sessions WHERE device_id = ? ORDER BY id DESC LIMIT 50",
        (device_id,),
    ).fetchall()
    return jsonify(items=[_screen_session_public(row) for row in rows])


@bp.get("/api/screen-sessions/<int:session_id>")
@require_operator
def get_screen_session(session_id: int):
    row = _operator_session(get_db(), session_id, g.operator["id"])
    if not row:
        return error("session_not_found", 404)
    return jsonify(_screen_session_public(row))


@bp.get("/api/screen-sessions/<int:session_id>/frame")
@require_operator
def get_screen_frame(session_id: int):
    row = _operator_session(get_db(), session_id, g.operator["id"])
    if not row:
        return error("session_not_found", 404)
    frame = _frame_path(session_id)
    if not frame.is_file():
        return error("frame_not_available", 404)
    return send_file(frame, mimetype="image/jpeg", conditional=False, max_age=0)


@bp.post("/api/screen-sessions/<int:session_id>/stop")
@require_operator
def stop_screen_session(session_id: int):
    db = get_db()
    row = _operator_session(db, session_id, g.operator["id"])
    if not row:
        return error("session_not_found", 404)
    if row["status"] in ("stopped", "declined", "expired"):
        return jsonify(_screen_session_public(row))
    now = utcnow()
    if row["status"] == "pending":
        db.execute(
            """UPDATE screen_sessions SET status = 'stopped', stop_requested_at = ?, stopped_at = ?
               WHERE id = ?""",
            (now, now, session_id),
        )
    else:
        db.execute(
            """UPDATE screen_sessions SET status = 'stopping', stop_requested_at = ?
               WHERE id = ? AND stop_requested_at IS NULL""",
            (now, session_id),
        )
    audit(db, "screen_session.stop_requested", operator_id=g.operator["id"],
          device_id=row["device_id"], detail=f"session={session_id}")
    db.commit()
    current = db.execute("SELECT * FROM screen_sessions WHERE id = ?", (session_id,)).fetchone()
    return jsonify(_screen_session_public(current))


@bp.get("/api/devices/me/screen-sessions")
@require_device
def my_screen_sessions():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM screen_sessions WHERE device_id = ? ORDER BY id DESC LIMIT 20",
        (g.device["id"],),
    ).fetchall()
    items = [_screen_session_public(row) for row in rows]
    pending = next((item for item in items if item["status"] == "pending"), None)
    active = next((item for item in items if item["status"] in ("active", "stopping")), None)
    return jsonify(items=items, pending=pending, active=active)


@bp.post("/api/devices/me/screen-sessions/<int:session_id>/approve")
@require_device
def approve_screen_session(session_id: int):
    data = request.get_json(silent=True) or {}
    consent = data.get("consent") if isinstance(data.get("consent"), dict) else {}
    if consent.get("accepted") is not True:
        return error("explicit_consent_required", 403)
    db = get_db()
    row = _device_session(db, session_id, g.device["id"])
    if not row or row["status"] != "pending":
        return error("session_not_pending", 409)
    now = utcnow()
    db.execute(
        """UPDATE screen_sessions SET status = 'stopped', stopped_at = ?
           WHERE device_id = ? AND id <> ? AND status IN ('active', 'stopping')""",
        (now, g.device["id"], session_id),
    )
    db.execute(
        """UPDATE screen_sessions
           SET status = 'active', approved_at = ?, connected_at = ?, last_seen_at = ?, consent_at = ?
           WHERE id = ?""",
        (now, now, now, str(consent.get("at") or now)[:40], session_id),
    )
    audit(db, "screen_session.approved_by_owner", operator_id=row["operator_id"],
          device_id=g.device["id"], detail=f"session={session_id}")
    db.commit()
    current = db.execute("SELECT * FROM screen_sessions WHERE id = ?", (session_id,)).fetchone()
    return jsonify(_screen_session_public(current))


@bp.post("/api/devices/me/screen-sessions/<int:session_id>/decline")
@require_device
def decline_screen_session(session_id: int):
    db = get_db()
    row = _device_session(db, session_id, g.device["id"])
    if not row or row["status"] != "pending":
        return error("session_not_pending", 409)
    now = utcnow()
    db.execute(
        "UPDATE screen_sessions SET status = 'declined', stopped_at = ? WHERE id = ?",
        (now, session_id),
    )
    audit(db, "screen_session.declined_by_owner", operator_id=row["operator_id"],
          device_id=g.device["id"], detail=f"session={session_id}")
    db.commit()
    return jsonify(ok=True)


@bp.post("/api/devices/me/screen-sessions/<int:session_id>/heartbeat")
@require_device
def screen_session_heartbeat(session_id: int):
    db = get_db()
    row = _device_session(db, session_id, g.device["id"])
    if not row or row["status"] not in ("active", "stopping"):
        return error("session_not_active", 409)
    now = utcnow()
    db.execute("UPDATE screen_sessions SET last_seen_at = ? WHERE id = ?", (now, session_id))
    db.commit()
    return jsonify(status=row["status"], stop_requested=bool(row["stop_requested_at"]))


@bp.post("/api/devices/me/screen-sessions/<int:session_id>/frame")
@require_device
def post_screen_frame(session_id: int):
    db = get_db()
    row = _device_session(db, session_id, g.device["id"])
    if not row or row["status"] != "active":
        return error("session_not_active", 409)
    if row["stop_requested_at"]:
        return error("session_stop_requested", 409)
    if request.mimetype != "image/jpeg":
        return error("jpeg_required", 415)
    data = request.get_data(cache=False)
    if not data or len(data) > int(current_app.config["MAX_CONTENT_LENGTH"]):
        return error("invalid_frame_size", 413)
    frame = _frame_path(session_id)
    temporary = frame.with_suffix(".jpg.tmp")
    temporary.write_bytes(data)
    temporary.replace(frame)
    now = utcnow()
    db.execute(
        """UPDATE screen_sessions
           SET frame_path = ?, last_frame_at = ?, last_seen_at = ?, connected_at = COALESCE(connected_at, ?)
           WHERE id = ?""",
        (str(frame), now, now, now, session_id),
    )
    db.commit()
    return jsonify(ok=True, bytes=len(data))


@bp.post("/api/devices/me/screen-sessions/<int:session_id>/stop")
@require_device
def device_stop_screen_session(session_id: int):
    db = get_db()
    row = _device_session(db, session_id, g.device["id"])
    if not row:
        return error("session_not_found", 404)
    now = utcnow()
    db.execute(
        "UPDATE screen_sessions SET status = 'stopped', stopped_at = ? WHERE id = ?",
        (now, session_id),
    )
    frame = _frame_path(session_id)
    if frame.is_file():
        frame.unlink(missing_ok=True)
    audit(db, "screen_session.stopped_by_owner", operator_id=row["operator_id"],
          device_id=g.device["id"], detail=f"session={session_id}")
    db.commit()
    return jsonify(ok=True)
