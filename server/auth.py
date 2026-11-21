"""Authentication: operator accounts/sessions and device bearer tokens."""
from __future__ import annotations

import functools
import re
import threading
import time
from collections import defaultdict

from flask import current_app, g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .util import add_hours, hash_token, new_token, utcnow

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")

_login_attempts: dict[str, list[float]] = defaultdict(list)
_login_lock = threading.Lock()
MAX_LOGIN_FAILURES = 10
LOGIN_WINDOW_SECONDS = 300


def login_allowed(ip: str) -> bool:
    """Lightweight per-IP throttle against password guessing."""
    now = time.monotonic()
    with _login_lock:
        recent = [t for t in _login_attempts[ip] if now - t < LOGIN_WINDOW_SECONDS]
        _login_attempts[ip] = recent
        return len(recent) < MAX_LOGIN_FAILURES


def record_login_failure(ip: str) -> None:
    with _login_lock:
        _login_attempts[ip].append(time.monotonic())


def clear_login_failures(ip: str) -> None:
    with _login_lock:
        _login_attempts.pop(ip, None)


def valid_username(username: str) -> bool:
    return bool(USERNAME_RE.match(username or ""))


def create_operator(username: str, password: str):
    if not valid_username(username):
        raise ValueError("Username must be 3-64 characters: letters, digits, dot, dash, underscore.")
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters.")
    db = get_db()
    cur = db.execute(
        "INSERT INTO operators (username, password_hash, created_at) VALUES (?,?,?)",
        (username, generate_password_hash(password), utcnow()),
    )
    db.commit()
    return cur.lastrowid


def find_operator(username: str):
    return get_db().execute("SELECT * FROM operators WHERE username = ?", (username,)).fetchone()


def check_operator_login(username: str, password: str):
    op = find_operator(username)
    if op and check_password_hash(op["password_hash"], password or ""):
        return op
    return None


def create_operator_session(operator_id: int) -> str:
    raw = new_token()
    db = get_db()
    db.execute(
        "INSERT INTO operator_sessions (operator_id, token_hash, created_at, expires_at) VALUES (?,?,?,?)",
        (operator_id, hash_token(raw), utcnow(), add_hours(current_app.config["OPERATOR_SESSION_TTL_HOURS"])),
    )
    db.commit()
    return raw


def operator_from_request():
    if "operator_id" in session:
        op = get_db().execute("SELECT * FROM operators WHERE id = ?", (session["operator_id"],)).fetchone()
        if op:
            return op
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        raw = header[7:].strip()
        db = get_db()
        row = db.execute(
            """SELECT o.* FROM operator_sessions s
               JOIN operators o ON o.id = s.operator_id
               WHERE s.token_hash = ? AND s.expires_at > ?""",
            (hash_token(raw), utcnow()),
        ).fetchone()
        if row:
            return row
    return None


def device_from_request():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    raw = header[7:].strip()
    row = get_db().execute(
        "SELECT * FROM devices WHERE token_hash = ? AND status = 'active' AND token_hash IS NOT NULL",
        (hash_token(raw),),
    ).fetchone()
    return row


def require_operator(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        op = operator_from_request()
        if op is None:
            if request.path.startswith("/api/"):
                return jsonify(error="authentication_required"), 401
            return redirect(url_for("dashboard.login"))
        g.operator = op
        return view(*args, **kwargs)

    return wrapped


def require_device(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        device = device_from_request()
        if device is None:
            return jsonify(error="invalid_or_revoked_device_token"), 401
        g.device = device
        return view(*args, **kwargs)

    return wrapped


def revoke_operator_session(raw: str) -> None:
    db = get_db()
    db.execute("DELETE FROM operator_sessions WHERE token_hash = ?", (hash_token(raw),))
    db.commit()
