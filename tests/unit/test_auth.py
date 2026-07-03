from app.config import get_settings
from app.models.user import User


async def _set_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    get_settings.cache_clear()


async def test_register_creates_user_with_user_role(client, monkeypatch):
    await _set_secret_key(monkeypatch)
    try:
        response = await client.post(
            "/auth/register", json={"email": "new@example.com", "password": "s3cr3tPass!"}
        )
        assert response.status_code == 201
        body = response.json()
        assert body["role"] == "user"
        assert "access_token" in body
    finally:
        get_settings.cache_clear()


async def test_register_ignores_role_in_request_body(client, monkeypatch):
    await _set_secret_key(monkeypatch)
    try:
        response = await client.post(
            "/auth/register",
            json={"email": "wannabe-admin@example.com", "password": "s3cr3tPass!", "role": "admin"},
        )
        assert response.status_code == 201
        assert response.json()["role"] == "user"
    finally:
        get_settings.cache_clear()


async def test_register_duplicate_email_is_rejected(client, monkeypatch):
    await _set_secret_key(monkeypatch)
    try:
        payload = {"email": "dupe@example.com", "password": "s3cr3tPass!"}
        first = await client.post("/auth/register", json=payload)
        assert first.status_code == 201
        second = await client.post("/auth/register", json=payload)
        assert second.status_code == 409
    finally:
        get_settings.cache_clear()


async def test_login_with_valid_credentials_issues_token(client, monkeypatch):
    await _set_secret_key(monkeypatch)
    try:
        await client.post("/auth/register", json={"email": "login@example.com", "password": "s3cr3tPass!"})
        response = await client.post(
            "/auth/token", data={"username": "login@example.com", "password": "s3cr3tPass!"}
        )
        assert response.status_code == 200
        assert response.json()["role"] == "user"
    finally:
        get_settings.cache_clear()


async def test_login_with_wrong_password_is_rejected(client, monkeypatch):
    await _set_secret_key(monkeypatch)
    try:
        await client.post("/auth/register", json={"email": "wrongpw@example.com", "password": "s3cr3tPass!"})
        response = await client.post(
            "/auth/token", data={"username": "wrongpw@example.com", "password": "not-the-password"}
        )
        assert response.status_code == 401
    finally:
        get_settings.cache_clear()


async def test_login_for_account_without_password_is_rejected(client, session, monkeypatch):
    await _set_secret_key(monkeypatch)
    try:
        session.add(User(email="social-only@example.com", password_hash=None, role="user"))
        await session.commit()
        response = await client.post(
            "/auth/token", data={"username": "social-only@example.com", "password": "anything"}
        )
        assert response.status_code == 401
    finally:
        get_settings.cache_clear()
