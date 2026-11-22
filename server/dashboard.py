"""Operator-facing Flask dashboard (Kali Linux side)."""
from __future__ import annotations

import json
import secrets
from pathlib import Path

from flask import (Blueprint, current_app, flash, g, jsonify, redirect,
                   render_template, request, send_file, session, url_for)

from .auth import (
    check_operator_login,
    clear_login_failures,
    login_allowed,
    record_login_failure,
    require_operator,
)
from .db import audit, get_db
from .util import add_hours, client_ip, hash_token, new_token, utcnow

bp = Blueprint("dashboard", __name__)


@bp.app_context_processor
def inject_csrf():
    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(24)
        return session["csrf"]

    return {"csrf_token": csrf_token, "app_name": "DARKPRIME"}


def check_csrf() -> bool:
    expected = session.get("csrf", "")
    provided = request.form.get("csrf", "")
    return bool(expected) and secrets.compare_digest(expected, provided)


def _latest_screen_session(device_id: int):
    return get_db().execute(
        """SELECT * FROM screen_sessions WHERE device_id = ? ORDER BY id DESC LIMIT 1""",
        (device_id,),
    ).fetchone()


def _screen_status_payload(row):
    if not row:
        return {"status": "none", "last_frame_at": None, "has_frame": False, "session_id": None}
    frame = Path(current_app.config["SCREEN_FRAME_DIR"]) / f"session-{row['id']}.jpg"
    return {
        "status": row["status"],
        "last_frame_at": row["last_frame_at"],
        "has_frame": frame.is_file(),
        "session_id": row["id"],
    }


@bp.get("/")
def index():
    if "operator_id" in session:
        return redirect(url_for("dashboard.devices"))
    return redirect(url_for("dashboard.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not check_csrf():
            return "invalid_csrf", 400
        ip = client_ip()
        if not login_allowed(ip):
            flash("Too many attempts. Try again in a few minutes.")
            return render_template("login.html")
        op = check_operator_login(request.form.get("username", ""), request.form.get("password", ""))
        if not op:
            record_login_failure(ip)
            audit(get_db(), "operator.login.failed", detail=f"dashboard ip={ip}")
            get_db().commit()
            flash("Invalid username or password.")
        else:
            clear_login_failures(ip)
            session.clear()
            session["operator_id"] = op["id"]
            session["csrf"] = secrets.token_urlsafe(24)
            db = get_db()
            audit(db, "operator.login", operator_id=op["id"], detail="dashboard")
            db.commit()
            return redirect(url_for("dashboard.devices"))
    return render_template("login.html")


@bp.post("/logout")
@require_operator
def logout():
    if not check_csrf():
        return "invalid_csrf", 400
    session.clear()
    return redirect(url_for("dashboard.login"))


@bp.get("/devices")
@require_operator
def devices():
    rows = get_db().execute(
        """SELECT d.*,
                  (SELECT COUNT(*) FROM alerts a WHERE a.device_id=d.id AND a.acknowledged_at IS NULL) AS open_alerts
           FROM devices d WHERE d.operator_id = ? ORDER BY d.id DESC""",
        (g.operator["id"],),
    ).fetchall()
    return render_template("devices.html", devices=rows)


@bp.get("/devices/<int:device_id>")
@require_operator
def device_detail(device_id: int):
    db = get_db()
    device = db.execute("SELECT * FROM devices WHERE id = ? AND operator_id = ?",
                        (device_id, g.operator["id"])).fetchone()
    if not device:
        return "Device not found", 404
    latest_row = db.execute(
        "SELECT payload, captured_at, received_at FROM telemetry WHERE device_id = ? ORDER BY id DESC LIMIT 1",
        (device_id,),
    ).fetchone()
    latest = json.loads(latest_row["payload"]) if latest_row else None
    alerts = db.execute(
        """SELECT * FROM alerts WHERE device_id = ?
           ORDER BY (acknowledged_at IS NULL) DESC,
                    CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 ELSE 3 END,
                    id DESC LIMIT 100""",
        (device_id,),
    ).fetchall()
    screen_session = _latest_screen_session(device_id)
    return render_template(
        "device_detail.html", device=device, latest=latest,
        received_at=latest_row["received_at"] if latest_row else None, alerts=alerts,
        screen_session=screen_session, screen_status=_screen_status_payload(screen_session),
    )


@bp.get("/devices/<int:device_id>/history")
@require_operator
def history(device_id: int):
    db = get_db()
    device = db.execute("SELECT * FROM devices WHERE id = ? AND operator_id = ?",
                        (device_id, g.operator["id"])).fetchone()
    if not device:
        return "Device not found", 404
    rows = db.execute(
        "SELECT id, captured_at, received_at, payload FROM telemetry WHERE device_id = ? ORDER BY id DESC LIMIT 200",
        (device_id,),
    ).fetchall()
    return render_template("history.html", device=device, reports=rows, json=json)


@bp.post("/devices/<int:device_id>/screen/request")
@require_operator
def screen_request(device_id: int):
    if not check_csrf():
        return "invalid_csrf", 400
    db = get_db()
    device = db.execute(
        "SELECT 1 FROM devices WHERE id = ? AND operator_id = ? AND status = 'active'",
        (device_id, g.operator["id"]),
    ).fetchone()
    if not device:
        return "Device not found", 404
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
    db.execute(
        """INSERT INTO screen_sessions (device_id, operator_id, status, requested_at)
           VALUES (?,?, 'pending', ?)""",
        (device_id, g.operator["id"], now),
    )
    audit(db, "screen_session.requested", operator_id=g.operator["id"], device_id=device_id,
          detail="dashboard")
    db.commit()
    flash("Screen sharing requested. The owner must approve it in the companion app.")
    return redirect(url_for("dashboard.device_detail", device_id=device_id))


@bp.post("/devices/<int:device_id>/screen/<int:session_id>/stop")
@require_operator
def screen_stop(device_id: int, session_id: int):
    if not check_csrf():
        return "invalid_csrf", 400
    db = get_db()
    row = db.execute(
        """SELECT s.* FROM screen_sessions s JOIN devices d ON d.id = s.device_id
           WHERE s.id = ? AND s.device_id = ? AND d.operator_id = ?""",
        (session_id, device_id, g.operator["id"]),
    ).fetchone()
    if not row:
        return "Session not found", 404
    if row["status"] not in ("stopped", "declined", "expired"):
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
              device_id=device_id, detail="dashboard")
        db.commit()
        flash("Stop requested. The app will end the session on its next check-in.")
    return redirect(url_for("dashboard.device_detail", device_id=device_id))


@bp.get("/devices/<int:device_id>/screen/status")
@require_operator
def screen_status(device_id: int):
    device = get_db().execute(
        "SELECT 1 FROM devices WHERE id = ? AND operator_id = ?",
        (device_id, g.operator["id"]),
    ).fetchone()
    if not device:
        return jsonify({"error": "device_not_found"}), 404
    return jsonify(_screen_status_payload(_latest_screen_session(device_id)))


@bp.get("/devices/<int:device_id>/screen/<int:session_id>/frame")
@require_operator
def screen_frame(device_id: int, session_id: int):
    row = get_db().execute(
        """SELECT s.* FROM screen_sessions s JOIN devices d ON d.id = s.device_id
           WHERE s.id = ? AND s.device_id = ? AND d.operator_id = ?""",
        (session_id, device_id, g.operator["id"]),
    ).fetchone()
    if not row:
        return "Session not found", 404
    frame = Path(current_app.config["SCREEN_FRAME_DIR"]) / f"session-{session_id}.jpg"
    if not frame.is_file():
        return "Frame not available", 404
    return send_file(frame, mimetype="image/jpeg", conditional=False, max_age=0)


@bp.route("/enroll", methods=["GET", "POST"])
@require_operator
def enroll():
    new_raw = None
    expires = None
    if request.method == "POST":
        if not check_csrf():
            return "invalid_csrf", 400
        new_raw = new_token(24)
        label = request.form.get("label", "")[:120]
        db = get_db()
        db.execute(
            """INSERT INTO enrollment_tokens (operator_id, token_hash, label, created_at, expires_at)
               VALUES (?,?,?,?,?)""",
            (g.operator["id"], hash_token(new_raw), label, utcnow(),
             add_hours(int(current_app.config["ENROLLMENT_TOKEN_TTL_HOURS"]))),
        )
        audit(db, "enrollment_token.created", operator_id=g.operator["id"], detail=label)
        db.commit()
        expires = current_app.config["ENROLLMENT_TOKEN_TTL_HOURS"]
    tokens = get_db().execute(
        """SELECT id, label, created_at, expires_at, used_at FROM enrollment_tokens
           WHERE operator_id = ? ORDER BY id DESC LIMIT 20""",
        (g.operator["id"],),
    ).fetchall()
    return render_template("enroll.html", new_token=new_raw, expires=expires, tokens=tokens)


@bp.get("/alerts")
@require_operator
def alerts():
    rows = get_db().execute(
        """SELECT a.*, d.name AS device_name FROM alerts a
           JOIN devices d ON d.id = a.device_id
           WHERE d.operator_id = ?
           ORDER BY (a.acknowledged_at IS NULL) DESC, a.id DESC LIMIT 300""",
        (g.operator["id"],),
    ).fetchall()
    return render_template("alerts.html", alerts=rows)


@bp.post("/alerts/<int:alert_id>/ack")
@require_operator
def ack_alert(alert_id: int):
    if not check_csrf():
        return "invalid_csrf", 400
    db = get_db()
    db.execute(
        """UPDATE alerts SET acknowledged_at = ? WHERE id = ? AND device_id IN
           (SELECT id FROM devices WHERE operator_id = ?)""",
        (utcnow(), alert_id, g.operator["id"]),
    )
    db.commit()
    target = request.form.get("next", "")
    if not target.startswith("/") or target.startswith("//"):
        target = url_for("dashboard.alerts")
    return redirect(target)


@bp.post("/devices/<int:device_id>/unenroll")
@require_operator
def unenroll(device_id: int):
    if not check_csrf():
        return "invalid_csrf", 400
    db = get_db()
    row = db.execute("SELECT * FROM devices WHERE id = ? AND operator_id = ?",
                     (device_id, g.operator["id"])).fetchone()
    if row and row["status"] == "active" and not row["unenroll_requested_at"]:
        db.execute("UPDATE devices SET unenroll_requested_at = ? WHERE id = ?", (utcnow(), device_id))
        audit(db, "device.unenroll_requested", operator_id=g.operator["id"], device_id=device_id)
        db.commit()
        flash("Unenrollment requested. The app will revoke the token on its next check-in.")
    return redirect(url_for("dashboard.device_detail", device_id=device_id))


@bp.get("/audit")
@require_operator
def audit_log():
    rows = get_db().execute(
        """SELECT a.*, d.name AS device_name FROM audit_log a
           LEFT JOIN devices d ON d.id = a.device_id
           WHERE a.operator_id = ? OR a.device_id IN (SELECT id FROM devices WHERE operator_id = ?)
           ORDER BY a.id DESC LIMIT 300""",
        (g.operator["id"], g.operator["id"]),
    ).fetchall()
    return render_template("audit.html", events=rows)
