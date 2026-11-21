"""Configuration for DARKPRIME. Values may be overridden with environment variables."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DARKPRIME_DATA_DIR", str(BASE_DIR / "data")))
DATABASE = Path(os.environ.get("DARKPRIME_DATABASE", str(DATA_DIR / "darkprime.sqlite3")))

SECRET_KEY = os.environ.get("DARKPRIME_SECRET_KEY", "dev-only-change-this-secret-key")
TOKEN_PEPPER = os.environ.get("DARKPRIME_TOKEN_PEPPER", "dev-only-change-this-pepper")
SESSION_COOKIE_SECURE = os.environ.get("DARKPRIME_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"}
REQUIRE_HTTPS = os.environ.get("DARKPRIME_REQUIRE_HTTPS", "0").lower() in {"1", "true", "yes"}
TRUST_PROXY = os.environ.get("DARKPRIME_TRUST_PROXY", "1").lower() in {"1", "true", "yes"}

ENROLLMENT_TOKEN_TTL_HOURS = int(os.environ.get("DARKPRIME_ENROLLMENT_TTL_HOURS", "72"))
OPERATOR_SESSION_TTL_HOURS = int(os.environ.get("DARKPRIME_SESSION_TTL_HOURS", "12"))
TELEMETRY_MAX_BYTES = int(os.environ.get("DARKPRIME_TELEMETRY_MAX_BYTES", str(1024 * 1024)))
MIN_TELEMETRY_INTERVAL_SECONDS = int(os.environ.get("DARKPRIME_MIN_TELEMETRY_INTERVAL", "15"))
POLL_INTERVAL_SECONDS = int(os.environ.get("DARKPRIME_POLL_INTERVAL", "900"))
MIN_SUPPORTED_ANDROID_SDK = int(os.environ.get("DARKPRIME_MIN_ANDROID_SDK", "26"))
MAX_APPS = int(os.environ.get("DARKPRIME_MAX_APPS", "1000"))

TLS_CERT = Path(os.environ.get("DARKPRIME_TLS_CERT", str(BASE_DIR / "server" / "certs" / "server.crt")))
TLS_KEY = Path(os.environ.get("DARKPRIME_TLS_KEY", str(BASE_DIR / "server" / "certs" / "server.key")))


def load_config() -> dict:
    return {
        "SECRET_KEY": SECRET_KEY,
        "TOKEN_PEPPER": TOKEN_PEPPER,
        "DATABASE": str(DATABASE),
        "DATA_DIR": str(DATA_DIR),
        "ENROLLMENT_TOKEN_TTL_HOURS": ENROLLMENT_TOKEN_TTL_HOURS,
        "OPERATOR_SESSION_TTL_HOURS": OPERATOR_SESSION_TTL_HOURS,
        "MAX_CONTENT_LENGTH": TELEMETRY_MAX_BYTES,
        "MIN_TELEMETRY_INTERVAL_SECONDS": MIN_TELEMETRY_INTERVAL_SECONDS,
        "POLL_INTERVAL_SECONDS": POLL_INTERVAL_SECONDS,
        "MIN_SUPPORTED_ANDROID_SDK": MIN_SUPPORTED_ANDROID_SDK,
        "MAX_APPS": MAX_APPS,
        "TLS_CERT": str(TLS_CERT),
        "TLS_KEY": str(TLS_KEY),
        "JSON_SORT_KEYS": False,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SECURE": SESSION_COOKIE_SECURE,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "PREFERRED_URL_SCHEME": "https" if SESSION_COOKIE_SECURE else "http",
        "REQUIRE_HTTPS": REQUIRE_HTTPS,
        "TRUST_PROXY": TRUST_PROXY,
    }
