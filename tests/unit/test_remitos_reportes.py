from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.models.productos import Productos

_SEQUENCE = ["en_produccion", "preparando", "listo_entregar", "en_entrega", "facturado"]


async def _make_cliente(session, idcliente, nom1="Juan", nom2="Garcia"):
    await session.execute(
        text("INSERT INTO clientes (idcliente, nom1, nom2) VALUES (:id, :nom1, :nom2)"),
        {"id": idcliente, "nom1": nom1, "nom2": nom2},
    )
    await session.commit()


async def _make_producto(session, **overrides):
    defaults = dict(codigo="P1", nombre="Pan", utilidad=10, precio_actual=100, lote_produccion=10, responsable="Ana")
    defaults.update(overrides)
    producto = Productos(**defaults)
    session.add(producto)
    await session.commit()
    await session.refresh(producto)
    return producto


async def _advance_to(client, remito_id, target):
    for estado in _SEQUENCE:
        resp = await client.patch(f"/costos/remitos/{remito_id}/estado", json={"nuevo_estado": estado})
        assert resp.status_code == 200, resp.json()
        if estado == target:
            break


async def test_pendientes_entrega_returns_all_remitos_regardless_of_estado(client, session):
    await _make_cliente(session, 1)
    now = datetime.now(timezone.utc)

    pendiente = await client.post(
        "/costos/remitos",
        json={"cliente_id": 1, "vendedor": "Ana", "fecha_entrega": now.isoformat(), "detalles": []},
    )
    facturado = await client.post(
        "/costos/remitos",
        json={
            "cliente_id": 1,
            "vendedor": "Ana",
            "fecha_entrega": (now + timedelta(days=1)).isoformat(),
            "detalles": [],
        },
    )
    await _advance_to(client, facturado.json()["id"], "facturado")

    response = await client.get("/costos/remitos-reportes/pendientes-entrega")
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert ids == [pendiente.json()["id"], facturado.json()["id"]]


async def test_pendientes_entrega_empty(client, session):
    response = await client.get("/costos/remitos-reportes/pendientes-entrega")
    assert response.status_code == 200
    assert response.json() == []


async def test_pendientes_por_dia_groups_and_counts_across_every_bucket(client, session):
    await _make_cliente(session, 2)
    day1 = datetime(2026, 1, 10, tzinfo=timezone.utc)
    day2 = datetime(2026, 1, 11, tzinfo=timezone.utc)

    async def _create(day):
        resp = await client.post(
            "/costos/remitos",
            json={"cliente_id": 2, "vendedor": "Ana", "fecha_entrega": day.isoformat(), "detalles": []},
        )
        return resp.json()["id"]

    # creado -> total_pendientes
    await _create(day1)
    # en_produccion -> total_en_preparacion
    await _advance_to(client, await _create(day1), "en_produccion")
    # preparando -> total_en_preparacion (merged with en_produccion)
    await _advance_to(client, await _create(day1), "preparando")
    # listo_entregar -> total_listo_para_entrega
    await _advance_to(client, await _create(day1), "listo_entregar")
    # en_entrega -> total_en_camino
    await _advance_to(client, await _create(day1), "en_entrega")
    # facturado -> total_entregados
    await _advance_to(client, await _create(day1), "facturado")
    # a second day, just a lone creado
    await _create(day2)

    response = await client.get("/costos/remitos-reportes/pendientes-por-dia")
    assert response.status_code == 200
    body = response.json()
    assert [g["fecha"] for g in body] == ["2026-01-10", "2026-01-11"]

    group1 = body[0]
    assert group1["total_remitos"] == 6
    assert group1["total_pendientes"] == 1
    assert group1["total_en_preparacion"] == 2
    assert group1["total_listo_para_entrega"] == 1
    assert group1["total_en_camino"] == 1
    assert group1["total_entregados"] == 1
    assert (
        group1["total_pendientes"]
        + group1["total_en_preparacion"]
        + group1["total_listo_para_entrega"]
        + group1["total_en_camino"]
        + group1["total_entregados"]
        == group1["total_remitos"]
    )

    group2 = body[1]
    assert group2["total_remitos"] == 1
    assert group2["total_pendientes"] == 1


async def test_pendientes_por_dia_filters_by_date_range(client, session):
    await _make_cliente(session, 3)
    day1 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    day2 = datetime(2026, 2, 5, tzinfo=timezone.utc)

    await client.post(
        "/costos/remitos",
        json={"cliente_id": 3, "vendedor": "Ana", "fecha_entrega": day1.isoformat(), "detalles": []},
    )
    await client.post(
        "/costos/remitos",
        json={"cliente_id": 3, "vendedor": "Ana", "fecha_entrega": day2.isoformat(), "detalles": []},
    )

    response = await client.get(
        "/costos/remitos-reportes/pendientes-por-dia",
        params={"fecha_desde": "2026-02-03T00:00:00Z"},
    )
    assert response.status_code == 200
    body = response.json()
    assert [g["fecha"] for g in body] == ["2026-02-05"]


async def test_productos_pendientes_por_dia_sums_pending_quantity(client, session):
    await _make_cliente(session, 4)
    producto = await _make_producto(session, nombre="Pan Frances", responsable="Carlos")
    now = datetime.now(timezone.utc)

    await client.post(
        "/costos/remitos",
        json={
            "cliente_id": 4,
            "vendedor": "Ana",
            "fecha_entrega": now.isoformat(),
            "detalles": [{"producto_id": producto.id, "cantidad": 10, "entregado": 4}],
        },
    )

    response = await client.get("/costos/remitos-reportes/productos-pendientes-por-dia")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["responsables"] == [
        {"responsable": "Carlos", "productos": [{"producto": "Pan Frances", "cantidad": 6}]}
    ]


async def test_productos_pendientes_por_dia_excludes_invoiced_remitos(client, session):
    await _make_cliente(session, 5)
    producto = await _make_producto(session, nombre="Medialuna")
    now = datetime.now(timezone.utc)

    created = await client.post(
        "/costos/remitos",
        json={
            "cliente_id": 5,
            "vendedor": "Ana",
            "fecha_entrega": now.isoformat(),
            "detalles": [{"producto_id": producto.id, "cantidad": 5}],
        },
    )
    await _advance_to(client, created.json()["id"], "facturado")

    response = await client.get("/costos/remitos-reportes/productos-pendientes-por-dia")
    assert response.status_code == 200
    assert response.json() == []


async def test_productos_pendientes_por_dia_groups_by_responsable_alphabetically(client, session):
    await _make_cliente(session, 6)
    producto_a = await _make_producto(session, nombre="Producto A", responsable="Zulema")
    producto_b = await _make_producto(session, nombre="Producto B", responsable="Alberto")
    now = datetime.now(timezone.utc)

    await client.post(
        "/costos/remitos",
        json={
            "cliente_id": 6,
            "vendedor": "Ana",
            "fecha_entrega": now.isoformat(),
            "detalles": [
                {"producto_id": producto_a.id, "cantidad": 3},
                {"producto_id": producto_b.id, "cantidad": 2},
            ],
        },
    )

    response = await client.get("/costos/remitos-reportes/productos-pendientes-por-dia")
    assert response.status_code == 200
    body = response.json()
    responsables = [r["responsable"] for r in body[0]["responsables"]]
    assert responsables == ["Alberto", "Zulema"]


async def test_productos_pendientes_por_dia_filters_by_date_range(client, session):
    await _make_cliente(session, 7)
    producto = await _make_producto(session, nombre="Pan Dulce")
    day1 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    day2 = datetime(2026, 3, 10, tzinfo=timezone.utc)

    await client.post(
        "/costos/remitos",
        json={
            "cliente_id": 7,
            "vendedor": "Ana",
            "fecha_entrega": day1.isoformat(),
            "detalles": [{"producto_id": producto.id, "cantidad": 3}],
        },
    )
    await client.post(
        "/costos/remitos",
        json={
            "cliente_id": 7,
            "vendedor": "Ana",
            "fecha_entrega": day2.isoformat(),
            "detalles": [{"producto_id": producto.id, "cantidad": 5}],
        },
    )

    response = await client.get(
        "/costos/remitos-reportes/productos-pendientes-por-dia",
        params={"fecha_desde": "2026-03-05"},
    )
    assert response.status_code == 200
    body = response.json()
    assert [g["fecha"] for g in body] == ["2026-03-10"]

    response = await client.get(
        "/costos/remitos-reportes/productos-pendientes-por-dia",
        params={"fecha_hasta": "2026-03-05"},
    )
    assert response.status_code == 200
    body = response.json()
    assert [g["fecha"] for g in body] == ["2026-03-01"]
