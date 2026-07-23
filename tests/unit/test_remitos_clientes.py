from datetime import datetime, timezone

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


async def test_remito_read_handles_cliente_with_null_nom2(client, session):
    await _make_cliente(session, 50, nom1="Solo Nombre", nom2=None)

    resp = await client.post(
        "/costos/remitos",
        json={
            "cliente_id": 50,
            "vendedor": "Ana",
            "fecha_entrega": datetime.now(timezone.utc).isoformat(),
            "detalles": [],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["cliente"]["nom1"] == "Solo Nombre"
    assert body["cliente"]["nom2"] is None


async def test_clientes_filter_by_nombre_matches_either_field(client, session):
    await _make_cliente(session, 1, nom1="Juan", nom2="Garcia")
    await _make_cliente(session, 2, nom1="Maria", nom2="Garciarena")
    await _make_cliente(session, 3, nom1="Pedro", nom2="Lopez")

    response = await client.get("/costos/clientes", params={"nombre": "garcia"})
    assert response.status_code == 200
    nombres = {(c["nom1"], c["nom2"]) for c in response.json()}
    assert nombres == {("Juan", "Garcia"), ("Maria", "Garciarena")}


async def test_clientes_q_alias_matches_either_field(client, session):
    await _make_cliente(session, 1, nom1="Juan", nom2="Garcia")
    await _make_cliente(session, 2, nom1="Maria", nom2="Garciarena")
    await _make_cliente(session, 3, nom1="Pedro", nom2="Lopez")

    response = await client.get("/costos/clientes", params={"q": "garcia"})
    assert response.status_code == 200
    nombres = {(c["nom1"], c["nom2"]) for c in response.json()}
    assert nombres == {("Juan", "Garcia"), ("Maria", "Garciarena")}


async def test_get_cliente_returns_full_record_shape(client, session):
    await session.execute(
        text(
            "INSERT INTO clientes (idcliente, nom1, nom2, cuit, direccion, localidad, provincia, "
            "tel1, celular, email1, personacontacto, activo) "
            "VALUES (99, 'Medialunas Calentitas', NULL, '20-1-1', 'Calle Falsa 123', 'CABA', "
            "'Buenos Aires', '4444-1111', '15-5555-5555', 'ventas@x.com', 'Ana', 1)"
        )
    )
    await session.commit()

    response = await client.get("/costos/clientes/99")
    assert response.status_code == 200
    assert response.json() == {
        "idcliente": 99,
        "nom1": "Medialunas Calentitas",
        "nom2": None,
        "cuit": "20-1-1",
        "direccion": "Calle Falsa 123",
        "localidad": "CABA",
        "provincia": "Buenos Aires",
        "tel1": "4444-1111",
        "celular": "15-5555-5555",
        "email1": "ventas@x.com",
        "personacontacto": "Ana",
        "activo": 1,
    }


async def test_create_remito_excludes_zero_quantity_lines(client, session):
    await _make_cliente(session, 10)
    producto_a = await _make_producto(session, nombre="Producto A")
    producto_b = await _make_producto(session, nombre="Producto B")

    response = await client.post(
        "/costos/remitos",
        json={
            "cliente_id": 10,
            "vendedor": "Ana",
            "fecha_entrega": datetime.now(timezone.utc).isoformat(),
            "detalles": [
                {"producto_id": producto_a.id, "cantidad": 5},
                {"producto_id": producto_b.id, "cantidad": 0},
            ],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["detalles"]) == 1
    assert body["detalles"][0]["producto_id"] == producto_a.id
    assert body["estado"] == "creado"


async def test_remito_estado_advances_through_transitions(client, session):
    await _make_cliente(session, 20)
    now = datetime.now(timezone.utc)

    created = await client.post(
        "/costos/remitos",
        json={"cliente_id": 20, "vendedor": "Ana", "fecha_entrega": now.isoformat(), "detalles": []},
    )
    rid = created.json()["id"]

    listo_entregar = await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "en_produccion"})
    assert listo_entregar.json()["estado"] == "en_produccion"
    await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "preparando"})
    listo_entregar = await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "listo_entregar"})
    assert listo_entregar.json()["estado"] == "listo_entregar"

    en_entrega = await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "en_entrega"})
    assert en_entrega.json()["estado"] == "en_entrega"

    facturado = await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "facturado"})
    assert facturado.json()["estado"] == "facturado"


async def test_list_remitos_filters_by_status(client, session):
    await _make_cliente(session, 30)
    now = datetime.now(timezone.utc)

    creado = await client.post(
        "/costos/remitos",
        json={"cliente_id": 30, "vendedor": "Ana", "fecha_entrega": now.isoformat(), "detalles": []},
    )
    en_entrega_remito = await client.post(
        "/costos/remitos",
        json={"cliente_id": 30, "vendedor": "Ana", "fecha_entrega": now.isoformat(), "detalles": []},
    )
    rid = en_entrega_remito.json()["id"]
    await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "en_produccion"})
    await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "preparando"})
    await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "listo_entregar"})
    await client.patch(f"/costos/remitos/{rid}/estado", json={"nuevo_estado": "en_entrega"})

    response = await client.get("/costos/remitos", params={"status": "creado"})
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert ids == [creado.json()["id"]]


async def test_list_remitos_filters_by_cliente_id(client, session):
    await _make_cliente(session, 31, nom1="Cliente Uno")
    await _make_cliente(session, 32, nom1="Cliente Dos")
    now = datetime.now(timezone.utc)

    match = await client.post(
        "/costos/remitos",
        json={"cliente_id": 31, "vendedor": "Ana", "fecha_entrega": now.isoformat(), "detalles": []},
    )
    await client.post(
        "/costos/remitos",
        json={"cliente_id": 32, "vendedor": "Ana", "fecha_entrega": now.isoformat(), "detalles": []},
    )

    response = await client.get("/costos/remitos", params={"cliente_id": 31})
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert ids == [match.json()["id"]]


async def test_list_remitos_orders_by_fecha_carga_descending(client, session):
    await _make_cliente(session, 33)
    now = datetime.now(timezone.utc)

    first = await client.post(
        "/costos/remitos",
        json={"cliente_id": 33, "vendedor": "Ana", "fecha_entrega": now.isoformat(), "detalles": []},
    )
    second = await client.post(
        "/costos/remitos",
        json={"cliente_id": 33, "vendedor": "Ana", "fecha_entrega": now.isoformat(), "detalles": []},
    )

    response = await client.get("/costos/remitos", params={"cliente_id": 33})
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert ids == [second.json()["id"], first.json()["id"]]


async def test_update_remito_replaces_detail_lines(client, session):
    await _make_cliente(session, 40)
    producto_a = await _make_producto(session, nombre="A")
    producto_b = await _make_producto(session, nombre="B")
    now = datetime.now(timezone.utc)

    created = await client.post(
        "/costos/remitos",
        json={
            "cliente_id": 40,
            "vendedor": "Ana",
            "fecha_entrega": now.isoformat(),
            "detalles": [{"producto_id": producto_a.id, "cantidad": 3}],
        },
    )
    remito_id = created.json()["id"]

    updated = await client.put(
        f"/costos/remitos/{remito_id}",
        json={"vendedor": "Ana Updated", "detalles": [{"producto_id": producto_b.id, "cantidad": 7}]},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["vendedor"] == "Ana Updated"
    assert len(body["detalles"]) == 1
    assert body["detalles"][0]["producto_id"] == producto_b.id
    assert body["detalles"][0]["cantidad"] == 7


async def test_update_remito_is_partial(client, session):
    await _make_cliente(session, 41)
    now = datetime.now(timezone.utc)

    created = await client.post(
        "/costos/remitos",
        json={"cliente_id": 41, "vendedor": "Ana", "observaciones": "Original", "fecha_entrega": now.isoformat(), "detalles": []},
    )
    remito_id = created.json()["id"]

    updated = await client.put(f"/costos/remitos/{remito_id}", json={"vendedor": "Nuevo Vendedor"})
    assert updated.status_code == 200
    body = updated.json()
    assert body["vendedor"] == "Nuevo Vendedor"
    assert body["observaciones"] == "Original"
