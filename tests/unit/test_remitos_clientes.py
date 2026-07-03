from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.models.productos import Productos


async def _make_cliente(session, idcliente, nom1="Juan", nom2="Garcia"):
    await session.execute(
        text("INSERT INTO clientes (idcliente, nom1, nom2) VALUES (:id, :nom1, :nom2)"),
        {"id": idcliente, "nom1": nom1, "nom2": nom2},
    )
    await session.commit()


async def _make_producto(session, **overrides):
    defaults = dict(codigo="P1", nombre="Pan", utilidad=10, precio_actual=100, lote_produccion=10)
    defaults.update(overrides)
    producto = Productos(**defaults)
    session.add(producto)
    await session.commit()
    await session.refresh(producto)
    return producto


async def test_clientes_filter_by_nombre_matches_either_field(client, session):
    await _make_cliente(session, 1, nom1="Juan", nom2="Garcia")
    await _make_cliente(session, 2, nom1="Maria", nom2="Garciarena")
    await _make_cliente(session, 3, nom1="Pedro", nom2="Lopez")

    response = await client.get("/costos/clientes", params={"nombre": "garcia"})
    assert response.status_code == 200
    nombres = {c["nombre"] for c in response.json()}
    assert nombres == {"Juan, Garcia", "Maria, Garciarena"}


async def test_create_remito_excludes_zero_quantity_lines(client, session):
    await _make_cliente(session, 10)
    producto_a = await _make_producto(session, nombre="Producto A")
    producto_b = await _make_producto(session, nombre="Producto B")

    response = await client.post(
        "/costos/remitos",
        json={
            "cliente": 10,
            "vendedor": "Ana",
            "fecha_entrega": datetime.now(timezone.utc).isoformat(),
            "productos": [
                {"producto": producto_a.id, "cantidad": 5},
                {"producto": producto_b.id, "cantidad": 0},
            ],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["productos"]) == 1
    assert body["productos"][0]["producto"] == producto_a.id
    assert body["estado"] == "PENDIENTE"


async def test_remito_estado_reflects_timestamps(client, session):
    await _make_cliente(session, 20)
    now = datetime.now(timezone.utc)

    en_camino = await client.post(
        "/costos/remitos",
        json={
            "cliente": 20,
            "vendedor": "Ana",
            "fecha_entrega": now.isoformat(),
            "fecha_despacho": now.isoformat(),
            "productos": [],
        },
    )
    assert en_camino.json()["estado"] == "EN CAMINO"

    entregado = await client.post(
        "/costos/remitos",
        json={
            "cliente": 20,
            "vendedor": "Ana",
            "fecha_entrega": now.isoformat(),
            "fecha_despacho": now.isoformat(),
            "fecha_recibido": now.isoformat(),
            "productos": [],
        },
    )
    assert entregado.json()["estado"] == "ENTREGADO"


async def test_list_remitos_filters_by_estado(client, session):
    await _make_cliente(session, 30)
    now = datetime.now(timezone.utc)

    pendiente = await client.post(
        "/costos/remitos",
        json={"cliente": 30, "vendedor": "Ana", "fecha_entrega": now.isoformat(), "productos": []},
    )
    await client.post(
        "/costos/remitos",
        json={
            "cliente": 30,
            "vendedor": "Ana",
            "fecha_entrega": now.isoformat(),
            "fecha_recibido": now.isoformat(),
            "productos": [],
        },
    )

    response = await client.get("/costos/remitos", params={"estado": "PENDIENTE"})
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert ids == [pendiente.json()["id"]]


async def test_update_remito_replaces_detail_lines(client, session):
    await _make_cliente(session, 40)
    producto_a = await _make_producto(session, nombre="A")
    producto_b = await _make_producto(session, nombre="B")
    now = datetime.now(timezone.utc)

    created = await client.post(
        "/costos/remitos",
        json={
            "cliente": 40,
            "vendedor": "Ana",
            "fecha_entrega": now.isoformat(),
            "productos": [{"producto": producto_a.id, "cantidad": 3}],
        },
    )
    remito_id = created.json()["id"]

    updated = await client.put(
        f"/costos/remitos/{remito_id}",
        json={
            "cliente": 40,
            "vendedor": "Ana Updated",
            "fecha_entrega": now.isoformat(),
            "productos": [{"producto": producto_b.id, "cantidad": 7}],
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["vendedor"] == "Ana Updated"
    assert len(body["productos"]) == 1
    assert body["productos"][0]["producto"] == producto_b.id
    assert body["productos"][0]["cantidad"] == 7
