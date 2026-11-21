"""Operator-facing Flask dashboard (Kali Linux side)."""
from __future__ import annotations

import json
import secrets

from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)

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
    return render_template("device_detail.html", device=device, latest=latest,
                           received_at=latest_row["received_at"] if latest_row else None, alerts=alerts)


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
