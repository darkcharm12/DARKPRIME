from server.tests.conftest import auth, enrolled_device, enrollment_token, login, payload


def test_telemetry_requires_device_token(client, app):
    device = enrolled_device(client, app)
    assert client.post("/api/devices/me/telemetry", json=payload()).status_code == 401
    assert client.post("/api/devices/me/telemetry", headers=auth("wrong"), json=payload()).status_code == 401
    assert client.post("/api/devices/me/telemetry", headers=auth(device["token"]), json={"bad": 1}).status_code == 400


def test_telemetry_creates_history_and_alerts(client, app):
    device = enrolled_device(client, app)
    headers = auth(device["token"])
    unsafe = payload(
        security={"accessibility_services": ["com.evil/Service"], "device_admins": [],
                  "screen_lock_secure": False, "usb_debugging": True,
                  "unknown_sources": False, "developer_options": False, "encryption_status": 0},
        storage={"total_bytes": 100, "free_bytes": 5, "free_percent": 5},
    )
    response = client.post("/api/devices/me/telemetry", headers=headers, json=unsafe)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["alerts_created"] >= 5

    op = login(client)
    alerts = client.get(f"/api/devices/{device['id']}/alerts", headers=auth(op)).get_json()["items"]
    codes = {a["code"] for a in alerts}
    assert {"ACCESSIBILITY_SERVICE", "NO_SCREEN_LOCK", "USB_DEBUGGING", "LOW_STORAGE", "NO_ENCRYPTION"} <= codes

    history = client.get(f"/api/devices/{device['id']}/history", headers=auth(op)).get_json()["items"]
    assert len(history) == 1
    assert history[0]["payload"]["device"]["model"] == "SM-S918B"


def test_alerts_are_deduplicated(client, app):
    device = enrolled_device(client, app)
    headers = auth(device["token"])
    data = payload(security={"accessibility_services": ["com.evil/Service"], "device_admins": [],
                             "screen_lock_secure": True, "usb_debugging": False,
                             "unknown_sources": False, "developer_options": False, "encryption_status": 2})
    first = client.post("/api/devices/me/telemetry", headers=headers, json=data).get_json()
    second = client.post("/api/devices/me/telemetry", headers=headers, json=data).get_json()
    assert first["alerts_created"] == 1
    assert second["alerts_created"] == 0


def test_app_changes_are_reported(client, app):
    device = enrolled_device(client, app)
    headers = auth(device["token"])
    client.post("/api/devices/me/telemetry", headers=headers, json=payload())
    changed = payload(apps=[{"package": "com.new.app", "label": "New", "version_name": "1",
                             "requested_permissions": ["android.permission.CAMERA"], "system": False}])
    response = client.post("/api/devices/me/telemetry", headers=headers, json=changed)
    assert response.get_json()["alerts_created"] >= 2
