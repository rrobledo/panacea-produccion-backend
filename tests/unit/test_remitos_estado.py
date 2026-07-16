from datetime import datetime, timezone

from sqlalchemy import text

from app.config import get_settings
from app.deps import require_api_key
from app.main import app


async def _make_cliente(session, idcliente, nom1="Juan", nom2="Garcia"):
    await session.execute(
        text("INSERT INTO clientes (idcliente, nom1, nom2) VALUES (:id, :nom1, :nom2)"),
        {"id": idcliente, "nom1": nom1, "nom2": nom2},
    )
    await session.commit()


async def _create_remito(client, cliente_id):
    now = datetime.now(timezone.utc)
    resp = await client.post(
        "/costos/remitos",
        json={"cliente_id": cliente_id, "vendedor": "Ana", "fecha_entrega": now.isoformat(), "detalles": []},
    )
    return resp.json()


async def test_valid_single_step_transition(client, session):
    await _make_cliente(session, 1)
    remito = await _create_remito(client, 1)

    resp = await client.patch(f"/costos/remitos/{remito['id']}/estado", json={"nuevo_estado": "en_produccion"})
    assert resp.status_code == 200
    assert resp.json()["estado"] == "en_produccion"


async def test_full_transition_sequence(client, session):
    await _make_cliente(session, 2)
    remito = await _create_remito(client, 2)
    rid = remito["id"]

    for next_estado in ["en_produccion", "preparando", "listo_entregar", "en_entrega", "facturado"]:
        resp = await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": next_estado})
        assert resp.status_code == 200, resp.json()
        assert resp.json()["estado"] == next_estado


async def test_skipped_transition_is_rejected(client, session):
    await _make_cliente(session, 3)
    remito = await _create_remito(client, 3)

    resp = await client.patch(f"/costos/remitos/{remito['id']}/estado", json={"nuevo_estado": "preparando"})
    assert resp.status_code == 422


async def test_backward_transition_is_rejected(client, session):
    await _make_cliente(session, 4)
    remito = await _create_remito(client, 4)
    rid = remito["id"]
    await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "en_produccion"})

    resp = await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "creado"})
    assert resp.status_code == 422


async def test_transition_without_api_key_is_rejected(client, session, monkeypatch):
    await _make_cliente(session, 5)
    remito = await _create_remito(client, 5)

    monkeypatch.setenv("API_KEYS", "realkey123")
    get_settings.cache_clear()
    app.dependency_overrides.pop(require_api_key, None)
    try:
        resp = await client.patch(f"/costos/remitos/{remito['id']}/estado", json={"nuevo_estado": "en_produccion"})
        assert resp.status_code == 401
    finally:
        get_settings.cache_clear()

    check = await client.get(f"/costos/remitos/{remito['id']}")
    assert check.json()["estado"] == "creado"


async def test_put_succeeds_while_creado(client, session):
    await _make_cliente(session, 6)
    remito = await _create_remito(client, 6)

    resp = await client.put(f"/costos/remitos/{remito['id']}", json={"vendedor": "Maria"})
    assert resp.status_code == 200
    assert resp.json()["vendedor"] == "Maria"


async def test_put_rejected_once_advanced(client, session):
    await _make_cliente(session, 7)
    remito = await _create_remito(client, 7)
    rid = remito["id"]
    await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "en_produccion"})

    resp = await client.put(f"/costos/remitos/{rid}", json={"vendedor": "Maria"})
    assert resp.status_code == 422

    check = await client.get(f"/costos/remitos/{rid}")
    assert check.json()["vendedor"] == "Ana"


async def test_delete_succeeds_while_creado(client, session):
    await _make_cliente(session, 8)
    remito = await _create_remito(client, 8)

    resp = await client.delete(f"/costos/remitos/{remito['id']}")
    assert resp.status_code == 204
    assert (await client.get(f"/costos/remitos/{remito['id']}")).status_code == 404


async def test_delete_rejected_once_advanced(client, session):
    await _make_cliente(session, 9)
    remito = await _create_remito(client, 9)
    rid = remito["id"]
    await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "en_produccion"})

    resp = await client.delete(f"/costos/remitos/{rid}")
    assert resp.status_code == 422
    assert (await client.get(f"/costos/remitos/{rid}")).status_code == 200
