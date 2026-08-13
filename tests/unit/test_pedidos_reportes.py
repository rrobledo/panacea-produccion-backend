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
    defaults = dict(codigo="P1", nombre="Pan", utilidad=10, precio_actual=100, lote_produccion=10, responsable="Ana")
    defaults.update(overrides)
    producto = Productos(**defaults)
    session.add(producto)
    await session.commit()
    await session.refresh(producto)
    return producto


async def _create_pedido(client, cliente_id, fecha_entrega, producto_id=None, cantidad_pedida=None):
    detalles = []
    if producto_id is not None:
        detalles = [{"producto_id": producto_id, "cantidad_pedida": cantidad_pedida}]
    resp = await client.post(
        "/costos/pedidos",
        json={
            "cliente_id": cliente_id,
            "vendedor": "Ana",
            "fecha_entrega": fecha_entrega.isoformat(),
            "detalles": detalles,
        },
    )
    return resp.json()


async def test_pendientes_por_dia_agrupa_y_cuenta_por_estado(client, session):
    await _make_cliente(session, 1)
    dia1 = datetime.now(timezone.utc)
    dia2 = dia1 + timedelta(days=1)

    pedido_a = await _create_pedido(client, 1, dia1)
    pedido_b = await _create_pedido(client, 1, dia1)
    pedido_c = await _create_pedido(client, 1, dia2)

    await client.patch(f"/costos/pedidos/{pedido_b['id']}/estado", json={"nuevo_estado": "EN_PREPARACION"})
    await client.patch(f"/costos/pedidos/{pedido_b['id']}/estado", json={"nuevo_estado": "PREPARADO"})
    await client.patch(f"/costos/pedidos/{pedido_c['id']}/estado", json={"nuevo_estado": "EN_PREPARACION"})

    resp = await client.get("/costos/pedidos-reportes/pendientes-por-dia")
    assert resp.status_code == 200
    body = {item["fecha"]: item for item in resp.json()}

    fecha1 = dia1.strftime("%Y-%m-%d")
    fecha2 = dia2.strftime("%Y-%m-%d")
    assert body[fecha1]["total_pedidos"] == 2
    assert body[fecha1]["total_pendientes"] == 1
    assert body[fecha1]["total_en_preparacion"] == 1
    assert body[fecha2]["total_pedidos"] == 1
    assert body[fecha2]["total_en_preparacion"] == 1


async def test_productos_pendientes_por_dia_excluye_pedidos_cerrados(client, session):
    await _make_cliente(session, 2)
    producto = await _make_producto(session)
    fecha = datetime.now(timezone.utc)

    entregado = await _create_pedido(client, 2, fecha, producto.id, 10)
    detalle_id = entregado["detalles"][0]["id"]
    await client.patch(f"/costos/pedidos/{entregado['id']}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 10}]})
    for estado in ["EN_PREPARACION", "PREPARADO", "LISTO_PARA_ENTREGA", "ENTREGADO"]:
        await client.patch(f"/costos/pedidos/{entregado['id']}/estado", json={"nuevo_estado": estado})

    cancelado = await _create_pedido(client, 2, fecha, producto.id, 5)
    await client.patch(f"/costos/pedidos/{cancelado['id']}/estado", json={"nuevo_estado": "CANCELADO"})

    pendiente = await _create_pedido(client, 2, fecha, producto.id, 10)
    detalle_id = pendiente["detalles"][0]["id"]
    await client.patch(f"/costos/pedidos/{pendiente['id']}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 4}]})

    resp = await client.get("/costos/pedidos-reportes/productos-pendientes-por-dia")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    responsables = body[0]["responsables"]
    assert len(responsables) == 1
    productos = responsables[0]["productos"]
    assert len(productos) == 1
    assert productos[0]["cantidad"] == 6


async def test_pendientes_entrega_devuelve_todos_ordenados_por_fecha(client, session):
    await _make_cliente(session, 3)
    fecha_tardia = datetime.now(timezone.utc) + timedelta(days=5)
    fecha_temprana = datetime.now(timezone.utc) + timedelta(days=1)

    tardio = await _create_pedido(client, 3, fecha_tardia)
    temprano = await _create_pedido(client, 3, fecha_temprana)

    resp = await client.get("/costos/pedidos-reportes/pendientes-entrega")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert ids.index(temprano["id"]) < ids.index(tardio["id"])
