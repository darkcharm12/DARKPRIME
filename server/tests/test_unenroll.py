from server.tests.conftest import auth, enrolled_device, login


def test_operator_request_then_device_confirm_revokes_token(client, app):
    device = enrolled_device(client, app)
    op = login(client)

    requested = client.post(f"/api/devices/{device['id']}/unenroll", headers=auth(op))
    assert requested.status_code == 200
    assert requested.get_json()["pending_actions"] == ["unenroll"]

    status = client.get("/api/devices/me", headers=auth(device["token"])).get_json()
    assert status["pending_actions"] == ["unenroll"]

    assert client.post("/api/devices/me/unenroll/confirm", headers=auth(device["token"])).status_code == 200
    assert client.get("/api/devices/me", headers=auth(device["token"])).status_code == 401
    assert client.post("/api/devices/me/telemetry", headers=auth(device["token"]),
                       json={"device": {}, "security": {}}).status_code == 401

    detail = client.get(f"/api/devices/{device['id']}", headers=auth(op)).get_json()["device"]
    assert detail["status"] == "unenrolled"


def test_device_owner_can_initiate_unenroll(client, app):
    device = enrolled_device(client, app)
    assert client.post("/api/devices/me/unenroll/request", headers=auth(device["token"])).status_code == 200
    assert client.get("/api/devices/me", headers=auth(device["token"])).get_json()["pending_actions"] == ["unenroll"]


def test_dashboard_flow(client, app):
    assert client.get("/devices").status_code == 302
    assert client.get("/login").status_code == 200
    with client.session_transaction() as sess:
        sess["csrf"] = "csrf-value"
    response = client.post("/login", data={"csrf": "csrf-value", "username": "operator",
                                           "password": "correct-horse-battery"})
    assert response.status_code == 302
    assert client.get("/devices").status_code == 200
    assert client.get("/enroll").status_code == 200
    assert client.get("/alerts").status_code == 200
    assert client.get("/audit").status_code == 200
