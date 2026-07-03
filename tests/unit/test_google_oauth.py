from app.auth.strategies import google as google_strategy
from app.config import get_settings
from app.models.user import User


async def _set_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FRONTEND_URLS", "https://front.example.com")
    get_settings.cache_clear()


async def test_initiate_redirects_to_google_with_signed_state(client, monkeypatch):
    await _set_secret_key(monkeypatch)
    try:
        response = await client.get("/auth/google", follow_redirects=False)
        assert response.status_code in (302, 307)
        location = response.headers["location"]
        assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "state=" in location
    finally:
        get_settings.cache_clear()


async def test_callback_with_existing_account_issues_token(client, session, monkeypatch):
    await _set_secret_key(monkeypatch)

    async def fake_exchange_code(code: str) -> dict:
        return {"email": "google-user@example.com", "name": "Google User"}

    monkeypatch.setattr(google_strategy, "_exchange_code", fake_exchange_code)

    session.add(User(email="google-user@example.com", password_hash=None, role="user", email_verified=True))
    await session.commit()

    try:
        state_resp = await client.get(
            "/auth/google", params={"redirect_uri": "https://front.example.com"}, follow_redirects=False
        )
        location = state_resp.headers["location"]
        state = location.split("state=")[1].split("&")[0]

        response = await client.get(
            "/auth/google/callback",
            params={"code": "fake-code", "state": state},
            follow_redirects=False,
        )
        assert response.status_code in (302, 307)
        assert "token=" in response.headers["location"]
    finally:
        get_settings.cache_clear()


async def test_callback_with_unknown_email_is_rejected(client, monkeypatch):
    await _set_secret_key(monkeypatch)

    async def fake_exchange_code(code: str) -> dict:
        return {"email": "nobody@example.com", "name": "Nobody"}

    monkeypatch.setattr(google_strategy, "_exchange_code", fake_exchange_code)

    try:
        state_resp = await client.get("/auth/google", follow_redirects=False)
        state = state_resp.headers["location"].split("state=")[1].split("&")[0]

        response = await client.get(
            "/auth/google/callback",
            params={"code": "fake-code", "state": state},
        )
        assert response.status_code == 404
    finally:
        get_settings.cache_clear()


async def test_callback_with_invalid_state_is_rejected(client, monkeypatch):
    await _set_secret_key(monkeypatch)
    try:
        response = await client.get(
            "/auth/google/callback",
            params={"code": "fake-code", "state": "not-a-valid-state-token"},
        )
        assert response.status_code == 400
    finally:
        get_settings.cache_clear()
