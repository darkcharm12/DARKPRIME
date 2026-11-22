from server.tests.conftest import (
    TEST_PASS,
    create_enrollment_token,
    enroll,
    operator_headers,
    sample_payload,
)


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["service"] == "DARKPRIME"


def test_authentication_required(client):
    assert client.get("/api/devices").status_code == 401
    response = client.post("/api/auth/login", json={"username": "operator", "password": "wrong"})
    assert response.status_code == 401
    assert response.get_json()["error"] == "invalid_credentials"


def test_enrollment_requires_explicit_consent(client):
    token = create_enrollment_token(client)
    response = enroll(client, token, consent=False)
    assert response.status_code == 403
    assert response.get_json()["error"] == "explicit_consent_required"


def test_enrollment_token_is_single_use(client):
    token = create_enrollment_token(client)
    first = enroll(client, token, uuid="device-a")
    assert first.status_code == 201
    body = first.get_json()
    assert body["device_id"] == 1
    assert body["token"]

    second = enroll(client, token, uuid="device-b")
    assert second.status_code == 409
    assert second.get_json()["error"] == "enrollment_token_already_used"

    duplicate_uuid = enroll(client, create_enrollment_token(client), uuid="device-a")
    assert duplicate_uuid.status_code == 201


def test_telemetry_history_and_alerts(client):
    token = create_enrollment_token(client)
    device = enroll(client, token).get_json()
    device_headers = {"Authorization": f"Bearer {device['token']}"}

    payload = sample_payload(accessibility=["com.evil/.Keylogger"])
    response = client.post("/api/devices/me/telemetry", json=payload, headers=device_headers)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["alerts_created"] >= 2

    ops = operator_headers(client)
    alerts = client.get(f"/api/devices/{device['device_id']}/alerts", headers=ops).get_json()["items"]
    codes = {a["code"] for a in alerts}
    assert "ACCESSIBILITY_SERVICE" in codes
    assert "LOW_STORAGE" in codes

    # Second snapshot with a new app triggers change detection.
    payload2 = sample_payload()
    payload2["apps"].append(
        {"package": "com.new", "label": "New App", "requested_permissions": ["android.permission.CAMERA"]}
    )
    second = client.post("/api/devices/me/telemetry", json=payload2, headers=device_headers)
    assert second.status_code == 200
    codes_now = {
        a["code"]
        for a in client.get(f"/api/devices/{device['device_id']}/alerts", headers=ops).get_json()["items"]
    }
    assert "APP_INSTALLED" in codes_now

    history = client.get(f"/api/devices/{device['device_id']}/history", headers=ops).get_json()["items"]
    assert len(history) == 2
    assert history[0]["payload"]["device"]["model"] == "SM-S918B"


def test_unenroll_revokes_device_token(client):
    token = create_enrollment_token(client)
    device = enroll(client, token).get_json()
    device_headers = {"Authorization": f"Bearer {device['token']}"}

    assert client.get("/api/devices/me", headers=device_headers).status_code == 200
    ops = operator_headers(client)
    requested = client.post(f"/api/devices/{device['device_id']}/unenroll", headers=ops)
    assert requested.status_code == 200
    assert "unenroll" in requested.get_json()["pending_actions"]

    confirmed = client.post("/api/devices/me/unenroll/confirm", json={}, headers=device_headers)
    assert confirmed.status_code == 200
    assert client.get("/api/devices/me", headers=device_headers).status_code == 401
    assert client.post("/api/devices/me/telemetry", json=sample_payload(), headers=device_headers).status_code == 401

    listing = client.get("/api/devices", headers=ops).get_json()["items"]
    assert listing[0]["status"] == "unenrolled"


def test_owner_can_request_unenroll(client):
    device = enroll(client, create_enrollment_token(client)).get_json()
    headers = {"Authorization": f"Bearer {device['token']}"}
    response = client.post("/api/devices/me/unenroll/request", json={}, headers=headers)
    assert response.status_code == 200
    assert "unenroll" in client.get("/api/devices/me", headers=headers).get_json()["pending_actions"]


def test_dashboard_login_csrf_and_pages(client):
    assert client.get("/devices").status_code == 302
    page = client.get("/login")
    assert page.status_code == 200
    csrf = page.get_data(as_text=True).split('name="csrf" value="')[1].split('"')[0]

    denied = client.post("/login", data={"username": "operator", "password": TEST_PASS})
    assert denied.status_code == 400

    signed_in = client.post(
        "/login",
        data={"username": "operator", "password": TEST_PASS, "csrf": csrf},
        follow_redirects=True,
    )
    assert signed_in.status_code == 200
    assert b"Enrolled devices" in signed_in.data

    enroll_page = client.get("/enroll")
    assert enroll_page.status_code == 200
    assert b"Create a one-time enrollment token" in enroll_page.data

    assert client.post("/logout").status_code == 400
    with client.session_transaction() as sess:
        active_csrf = sess["csrf"]
    assert client.post("/logout", data={"csrf": active_csrf}).status_code == 302
    assert client.get("/devices").status_code == 302


def test_application_requires_https_when_configured(app):
    from server.app import create_app

    try:
        create_app(
            {
                "REQUIRE_HTTPS": True,
                "SECRET_KEY": "dev-only-change-this-secret-key",
                "TOKEN_PEPPER": "dev-only-change-this-pepper",
                "DATABASE": app.config["DATABASE"],
            }
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("default secrets must be rejected in production mode")

    secure_app = create_app(
        {
            "REQUIRE_HTTPS": True,
            "SECRET_KEY": "test-secret-key",
            "TOKEN_PEPPER": "test-token-pepper",
            "DATABASE": app.config["DATABASE"],
        }
    )
    secure = secure_app.test_client()
    assert secure.get("/api/health").status_code == 403
