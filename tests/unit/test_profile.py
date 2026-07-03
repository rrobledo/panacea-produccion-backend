from app.config import get_settings


async def _set_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    get_settings.cache_clear()


async def test_profile_me_returns_current_user(client, monkeypatch):
    await _set_secret_key(monkeypatch)
    try:
        register = await client.post(
            "/auth/register", json={"email": "profile-me@example.com", "password": "s3cr3tPass!"}
        )
        token = register.json()["access_token"]

        response = await client.get("/profile/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "profile-me@example.com"
        assert body["role"] == "user"
        assert body["email_verified"] is False
        assert "password_hash" not in body
    finally:
        get_settings.cache_clear()


async def test_profile_me_requires_authentication(client, monkeypatch):
    await _set_secret_key(monkeypatch)
    try:
        response = await client.get("/profile/me")
        assert response.status_code == 401
    finally:
        get_settings.cache_clear()
