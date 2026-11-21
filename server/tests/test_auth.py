from server.tests.conftest import auth, enrolled_device, enrollment_token, login, payload


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_login_success_and_failure(client):
    assert client.post("/api/auth/login", json={"username": "operator", "password": "wrong"}).status_code == 401
    response = client.post("/api/auth/login", json={"username": "operator", "password": "correct-horse-battery"})
    assert response.status_code == 200
    assert response.get_json()["operator"]["username"] == "operator"


def test_operator_endpoints_require_auth(client):
    assert client.get("/api/devices").status_code == 401
    assert client.get("/api/enrollment-tokens").status_code == 401


def test_create_enrollment_token_via_api(client):
    token = login(client)
    response = client.post("/api/enrollment-tokens", headers=auth(token), json={"label": "phone"})
    assert response.status_code == 201
    assert response.get_json()["token"]

    listing = client.get("/api/enrollment-tokens", headers=auth(token)).get_json()
    assert listing["items"][0]["label"] == "phone"
