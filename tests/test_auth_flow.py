from opsweave.api import user_store


def test_register_login_me_logout_flow(client):
    client.app.dependency_overrides.clear()
    registered = client.post(
        "/api/auth/register", json={"username": "newuser", "password": "correct-horse"}
    )
    assert registered.status_code == 201
    assert (
        client.post(
            "/api/auth/register",
            json={"username": "newuser", "password": "correct-horse"},
        ).status_code
        == 409
    )

    login = client.post(
        "/api/auth/login", json={"username": "newuser", "password": "correct-horse"}
    )
    assert login.status_code == 200
    token = client.cookies.get("opsweave_session")
    assert token
    assert client.get("/api/auth/me").json() == {
        "username": "newuser",
        "role": "viewer",
    }

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert user_store.user_for_token(token) is None


def test_login_rejects_invalid_credentials(client):
    client.app.dependency_overrides.clear()
    client.post(
        "/api/auth/register", json={"username": "newuser", "password": "correct-horse"}
    )
    response = client.post(
        "/api/auth/login",
        json={"username": "newuser", "password": "incorrect-password"},
    )
    assert response.status_code == 401
