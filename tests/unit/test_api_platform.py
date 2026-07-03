from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.deps import require_api_key, require_cron_secret
from app.main import app


async def test_accept_write_with_valid_api_key(client, monkeypatch):
    # Unlike every other test's `client` fixture (which bypasses
    # require_api_key entirely via a dependency override), this exercises
    # the real dependency end to end against a real configured key —
    # otherwise "a valid key is accepted" was never actually proven,
    # only "no key is rejected".
    monkeypatch.setenv("API_KEYS", "realkey123")
    get_settings.cache_clear()
    app.dependency_overrides.pop(require_api_key, None)
    try:
        response = await client.post(
            "/costos/proveedores",
            json={"nombre": "Valid Key Co", "cuit": "99-1-1"},
            headers={"X-API-Key": "realkey123"},
        )
        assert response.status_code == 201
    finally:
        get_settings.cache_clear()


async def test_cron_endpoint_rejects_general_api_key_alone(client, monkeypatch):
    monkeypatch.setenv("API_KEYS", "frontendkey")
    monkeypatch.setenv("CRON_SECRET", "realcronsecret")
    get_settings.cache_clear()
    app.dependency_overrides.pop(require_cron_secret, None)
    try:
        response = await client.post(
            "/internal/cron/monthly-cascade", headers={"X-API-Key": "frontendkey"}
        )
        assert response.status_code == 401
    finally:
        get_settings.cache_clear()


async def test_cors_rejects_unlisted_origin(session):
    from app.deps import get_session

    async def _get_session_override():
        yield session

    app.dependency_overrides[get_session] = _get_session_override
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/health", headers={"Origin": "http://evil.example.com"})
        assert "access-control-allow-origin" not in response.headers
    finally:
        app.dependency_overrides.clear()
