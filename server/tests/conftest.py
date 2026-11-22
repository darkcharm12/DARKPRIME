from __future__ import annotations

import pytest

from server.app import create_app
from server.auth import create_operator
from server.db import get_db, init_db
from server.util import add_hours, hash_token, new_token, utcnow

TEST_USER = "operator"
TEST_PASS = "correct-horse-battery"


@pytest.fixture()
def app(tmp_path):
    database = tmp_path / "test.sqlite3"
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(database),
            "SECRET_KEY": "test-secret-key",
            "TOKEN_PEPPER": "test-token-pepper",
            "MIN_TELEMETRY_INTERVAL_SECONDS": 0,
            "OPERATOR_SESSION_TTL_HOURS": 12,
            "ENROLLMENT_TOKEN_TTL_HOURS": 72,
            "POLL_INTERVAL_SECONDS": 900,
            "MIN_SUPPORTED_ANDROID_SDK": 26,
            "SCREEN_FRAME_DIR": str(tmp_path / "screen_frames"),
            "TRUST_PROXY": False,
        }
    )
    with application.app_context():
        init_db(str(database))
        create_operator(TEST_USER, TEST_PASS)
        get_db().commit()
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username=TEST_USER, password=TEST_PASS) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def operator_headers(client) -> dict:
    return auth(login(client))


def enrollment_token(app, label="test") -> str:
    raw = new_token(24)
    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT INTO enrollment_tokens (operator_id, token_hash, label, created_at, expires_at)
               VALUES (1, ?, ?, ?, ?)""",
            (hash_token(raw), label, utcnow(), add_hours(72)),
        )
        db.commit()
    return raw


def create_enrollment_token(client, headers=None) -> str:
    headers = headers or operator_headers(client)
    response = client.post("/api/enrollment-tokens", json={"label": "test"}, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["token"]


def enroll(client, token: str, uuid: str = "test-device-1", consent: bool = True):
    return client.post(
        "/api/devices/enroll",
        json={
            "enrollment_token": token,
            "device_uuid": uuid,
            "name": "Test Samsung",
            "model": "SM-S918B",
            "android_version": "14",
            "client_version": "1.0.0",
            "consent": {"accepted": consent, "at": utcnow()},
        },
    )


def enrolled_device(client, app, uuid="test-uuid-1"):
    response = enroll(client, enrollment_token(app), uuid=uuid)
    assert response.status_code == 201, response.get_json()
    body = response.get_json()
    return {"id": body["device_id"], "token": body["token"]}


def payload(**overrides) -> dict:
    data = {
        "captured_at": utcnow(),
        "client_version": "1.0.0",
        "device": {
            "model": "SM-S918B",
            "brand": "samsung",
            "android_version": "14",
            "sdk": 34,
            "security_patch": "2026-01-01",
        },
        "battery": {"level": 80, "charging": True},
        "storage": {"total_bytes": 1000, "free_bytes": 500, "free_percent": 50},
        "apps": [
            {
                "package": "com.example.app",
                "label": "Example",
                "version_name": "1.2",
                "requested_permissions": ["android.permission.INTERNET"],
                "system": False,
            }
        ],
        "security": {
            "accessibility_services": [],
            "device_admins": [],
            "screen_lock_secure": True,
            "usb_debugging": False,
            "unknown_sources": False,
            "developer_options": False,
            "encryption_status": 2,
        },
        "network": {"type": "wifi"},
    }
    data.update(overrides)
    return data


def sample_payload(apps=None, accessibility=None) -> dict:
    data = payload()
    data["storage"] = {"total_bytes": 1000, "free_bytes": 50, "free_percent": 5}
    if apps is not None:
        data["apps"] = apps
    if accessibility is not None:
        data["security"]["accessibility_services"] = accessibility
    return data
