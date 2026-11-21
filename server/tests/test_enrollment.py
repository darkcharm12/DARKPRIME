from server.tests.conftest import auth, enrolled_device, enrollment_token, login, payload, utcnow


def test_enrollment_requires_explicit_consent(client, app):
    raw = enrollment_token(app)
    response = client.post("/api/devices/enroll", json={
        "enrollment_token": raw, "device_uuid": "no-consent", "consent": {"accepted": False},
    })
    assert response.status_code == 403
    assert response.get_json()["error"] == "explicit_consent_required"


def test_enrollment_rejects_unknown_and_reused_tokens(client, app):
    response = client.post("/api/devices/enroll", json={
        "enrollment_token": "not-a-token", "device_uuid": "bad-token", "consent": {"accepted": True, "at": utcnow()},
    })
    assert response.status_code == 401

    device = enrolled_device(client, app)
    raw = enrollment_token(app)
    first = client.post("/api/devices/enroll", json={
        "enrollment_token": raw, "device_uuid": "reuse-1", "consent": {"accepted": True, "at": utcnow()},
    })
    assert first.status_code == 201
    second = client.post("/api/devices/enroll", json={
        "enrollment_token": raw, "device_uuid": "reuse-2", "consent": {"accepted": True, "at": utcnow()},
    })
    assert second.status_code == 409
    assert device["token"]


def test_duplicate_uuid_rejected(client, app):
    enrolled_device(client, app, uuid="duplicate")
    response = client.post("/api/devices/enroll", json={
        "enrollment_token": enrollment_token(app), "device_uuid": "duplicate", "consent": {"accepted": True},
    })
    assert response.status_code == 409
