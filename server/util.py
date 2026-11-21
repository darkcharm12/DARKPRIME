"""Small shared helpers for time, tokens and request metadata."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, request


def utcnow() -> str:
    """Return a compact, sortable UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    """Parse timestamps produced by :func:`utcnow` (and common ISO variants)."""
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def add_hours(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=int(hours))).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def new_token(nbytes: int = 32) -> str:
    """URL-safe, high-entropy token. Only its hash is ever stored."""
    return secrets.token_urlsafe(nbytes)


def hash_token(raw: str) -> str:
    """Hash a bearer token with the server-side pepper.

    A pepper means a database leak alone cannot reconstruct usable tokens.
    """
    pepper = str(current_app.config.get("TOKEN_PEPPER", ""))
    return hashlib.sha256((pepper + "\x00" + str(raw)).encode("utf-8")).hexdigest()


def client_ip() -> str:
    """Return the apparent client IP, preferring the reverse-proxy header."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:64]
    return (request.remote_addr or "unknown")[:64]
