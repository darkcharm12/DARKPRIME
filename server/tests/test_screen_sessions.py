from server.tests.conftest import (
    TEST_PASS,
    create_enrollment_token,
    enroll,
    operator_headers,
)


def _device(client):
    enrolled = enroll(client, create_enrollment_token(client)).get_json()
    return enrolled, {"Authorization": f"Bearer {enrolled['token']}"}


def _login_dashboard(client):
    page = client.get("/login")
    csrf = page.get_data(as_text=True).split('name="csrf" value="')[1].split('"')[0]
    client.post(
        "/login",
        data={"username": "operator", "password": TEST_PASS, "csrf": csrf},
        follow_redirects=True,
    )
    with client.session_transaction() as session:
        return session["csrf"]


def test_screen_session_requires_owner_approval_and_visible_stop(client):
    device, device_headers = _device(client)
    ops = operator_headers(client)
    device_id = device["device_id"]

    requested = client.post(f"/api/devices/{device_id}/screen-sessions", headers=ops)
    assert requested.status_code == 201
    session = requested.get_json()
    assert session["status"] == "pending"

    assert "screen_session" in client.get("/api/devices/me", headers=device_headers).get_json()["pending_actions"]
    mine = client.get("/api/devices/me/screen-sessions", headers=device_headers).get_json()
    assert mine["pending"]["id"] == session["id"]

    denied = client.post(
        f"/api/devices/me/screen-sessions/{session['id']}/approve",
        json={"consent": {"accepted": False}},
        headers=device_headers,
    )
    assert denied.status_code == 403
    assert denied.get_json()["error"] == "explicit_consent_required"

    approved = client.post(
        f"/api/devices/me/screen-sessions/{session['id']}/approve",
        json={"consent": {"accepted": True, "at": "2026-11-22T00:00:00Z"}},
        headers=device_headers,
    )
    assert approved.status_code == 200
    assert approved.get_json()["status"] == "active"
    assert client.get(f"/api/screen-sessions/{session['id']}/frame", headers=ops).status_code == 404

    frame = client.post(
        f"/api/devices/me/screen-sessions/{session['id']}/frame",
        data=b"fake-jpeg",
        content_type="image/jpeg",
        headers=device_headers,
    )
    assert frame.status_code == 200
    served = client.get(f"/api/screen-sessions/{session['id']}/frame", headers=ops)
    assert served.status_code == 200
    assert served.data == b"fake-jpeg"

    heartbeat = client.post(
        f"/api/devices/me/screen-sessions/{session['id']}/heartbeat",
        json={},
        headers=device_headers,
    )
    assert heartbeat.get_json() == {"status": "active", "stop_requested": False}

    stopped = client.post(f"/api/screen-sessions/{session['id']}/stop", headers=ops)
    assert stopped.status_code == 200
    assert stopped.get_json()["status"] == "stopping"
    heartbeat = client.post(
        f"/api/devices/me/screen-sessions/{session['id']}/heartbeat",
        json={},
        headers=device_headers,
    )
    assert heartbeat.get_json() == {"status": "stopping", "stop_requested": True}
    upload_after_stop = client.post(
        f"/api/devices/me/screen-sessions/{session['id']}/frame",
        data=b"later-jpeg",
        content_type="image/jpeg",
        headers=device_headers,
    )
    assert upload_after_stop.status_code == 409

    finished = client.post(
        f"/api/devices/me/screen-sessions/{session['id']}/stop",
        json={},
        headers=device_headers,
    )
    assert finished.status_code == 200
    current = client.get(f"/api/screen-sessions/{session['id']}", headers=ops).get_json()
    assert current["status"] == "stopped"
    assert current["stopped_at"]


def test_screen_session_decline_and_pending_stop(client):
    device, device_headers = _device(client)
    ops = operator_headers(client)
    device_id = device["device_id"]

    first = client.post(f"/api/devices/{device_id}/screen-sessions", headers=ops).get_json()
    declined = client.post(
        f"/api/devices/me/screen-sessions/{first['id']}/decline",
        json={},
        headers=device_headers,
    )
    assert declined.status_code == 200
    assert client.get(f"/api/screen-sessions/{first['id']}", headers=ops).get_json()["status"] == "declined"

    second = client.post(f"/api/devices/{device_id}/screen-sessions", headers=ops).get_json()
    stopped = client.post(f"/api/screen-sessions/{second['id']}/stop", headers=ops)
    assert stopped.get_json()["status"] == "stopped"
    late = client.post(
        f"/api/devices/me/screen-sessions/{second['id']}/approve",
        json={"consent": {"accepted": True}},
        headers=device_headers,
    )
    assert late.status_code == 409


def test_screen_session_apis_enforce_operator_device_separation(client):
    device, device_headers = _device(client)
    ops = operator_headers(client)
    session = client.post(
        f"/api/devices/{device['device_id']}/screen-sessions", headers=ops
    ).get_json()

    assert client.get(f"/api/screen-sessions/{session['id']}").status_code == 401
    assert client.post(
        f"/api/screen-sessions/{session['id']}/stop", headers=device_headers
    ).status_code == 401
    assert client.post(
        f"/api/devices/me/screen-sessions/{session['id']}/approve",
        json={"consent": {"accepted": True}},
        headers=ops,
    ).status_code == 401


def test_dashboard_shows_and_controls_screen_sessions(client):
    device, _ = _device(client)
    csrf = _login_dashboard(client)
    detail_url = f"/devices/{device['device_id']}"

    assert client.get(detail_url).status_code == 200
    assert b"Remote screen session" in client.get(detail_url).data
    assert client.post(f"{detail_url}/screen/request", data={}).status_code == 400

    response = client.post(
        f"{detail_url}/screen/request",
        data={"csrf": csrf},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Screen sharing requested" in response.data
    assert b"pending" in response.data

    status = client.get(f"{detail_url}/screen/status").get_json()
    assert status["status"] == "pending"
    assert status["session_id"]

    stop = client.post(
        f"{detail_url}/screen/{status['session_id']}/stop",
        data={"csrf": csrf},
        follow_redirects=True,
    )
    assert stop.status_code == 200
    assert b"Stop requested" in stop.data
