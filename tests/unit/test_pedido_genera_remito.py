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


async def _create_pedido(client, cliente_id, producto_id, cantidad_pedida):
    now = datetime.now(timezone.utc)
    resp = await client.post(
        "/costos/pedidos",
        json={
            "cliente_id": cliente_id,
            "vendedor": "Ana",
            "fecha_entrega": now.isoformat(),
            "detalles": [{"producto_id": producto_id, "cantidad_pedida": cantidad_pedida}],
        },
    )
    return resp.json()


async def _avanzar_hasta_preparado(client, pedido_id):
    for estado in ["EN_PREPARACION", "PREPARADO"]:
        resp = await client.patch(f"/costos/pedidos/{pedido_id}/estado", json={"nuevo_estado": estado})
        assert resp.status_code == 200, resp.json()


async def _make_sucursal(client, nombre, tipo="SUCURSAL"):
    resp = await client.post("/costos/sucursales", json={"nombre": nombre, "tipo": tipo})
    return resp.json()["id"]


async def _create_pedido_sucursal(client, sucursal_id, producto_id, cantidad_pedida):
    now = datetime.now(timezone.utc)
    resp = await client.post(
        "/costos/pedidos",
        json={
            "tipo": "SUCURSAL",
            "sucursal_id": sucursal_id,
            "vendedor": "Ana",
            "fecha_entrega": now.isoformat(),
            "detalles": [{"producto_id": producto_id, "cantidad_pedida": cantidad_pedida}],
        },
    )
    return resp.json()


async def test_transicion_genera_remito_con_lo_entregado(client, session):
    await _make_cliente(session, 1)
    producto = await _make_producto(session)
    pedido = await _create_pedido(client, 1, producto.id, 10)
    detalle_id = pedido["detalles"][0]["id"]

    await client.patch(
        f"/costos/pedidos/{pedido['id']}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 6}]}
    )
    await _avanzar_hasta_preparado(client, pedido["id"])

    resp = await client.patch(f"/costos/pedidos/{pedido['id']}/estado", json={"nuevo_estado": "LISTO_PARA_ENTREGA"})
    assert resp.status_code == 200, resp.json()

    remitos = (await client.get("/costos/remitos", params={"pedido_id": pedido["id"]})).json()
    assert len(remitos) == 1
    assert remitos[0]["tipo"] == "VENTA"
    assert remitos[0]["pedido_id"] == pedido["id"]
    assert remitos[0]["estado"] == "RECIBIDO"
    assert remitos[0]["detalles"][0]["cantidad"] == 6


async def test_segunda_tanda_genera_segundo_remito(client, session):
    await _make_cliente(session, 2)
    producto = await _make_producto(session)
    pedido = await _create_pedido(client, 2, producto.id, 10)
    pid = pedido["id"]
    detalle_id = pedido["detalles"][0]["id"]

    await client.patch(f"/costos/pedidos/{pid}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 6}]})
    await _avanzar_hasta_preparado(client, pid)
    await client.patch(f"/costos/pedidos/{pid}/estado", json={"nuevo_estado": "LISTO_PARA_ENTREGA"})

    await client.patch(f"/costos/pedidos/{pid}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 10}]})
    resp = await client.patch(f"/costos/pedidos/{pid}/estado", json={"nuevo_estado": "ENTREGADO"})
    assert resp.status_code == 200, resp.json()

    remitos = (await client.get("/costos/remitos", params={"pedido_id": pid})).json()
    assert len(remitos) == 2
    cantidades = sorted(r["detalles"][0]["cantidad"] for r in remitos)
    assert cantidades == [4, 6]
    assert all(r["estado"] == "RECIBIDO" for r in remitos)


async def test_transicion_sin_entrega_nueva_no_genera_segundo_remito(client, session):
    # A pedido delivered in full at LISTO_PARA_ENTREGA has nothing left to
    # ship by the time it reaches ENTREGADO — that step must still succeed
    # (it's just an administrative state change), but without creating a
    # second, empty remito. Only the very first remito-generating
    # transition is rejected when nothing was ever delivered (see
    # test_transicion_sin_ninguna_entrega_es_rechazada below).
    await _make_cliente(session, 3)
    producto = await _make_producto(session)
    pedido = await _create_pedido(client, 3, producto.id, 10)
    pid = pedido["id"]
    detalle_id = pedido["detalles"][0]["id"]

    await client.patch(f"/costos/pedidos/{pid}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 6}]})
    await _avanzar_hasta_preparado(client, pid)
    resp = await client.patch(f"/costos/pedidos/{pid}/estado", json={"nuevo_estado": "LISTO_PARA_ENTREGA"})
    assert resp.status_code == 200, resp.json()

    resp = await client.patch(f"/costos/pedidos/{pid}/estado", json={"nuevo_estado": "ENTREGADO"})
    assert resp.status_code == 200, resp.json()

    remitos = (await client.get("/costos/remitos", params={"pedido_id": pid})).json()
    assert len(remitos) == 1


async def test_transicion_sin_ninguna_entrega_es_rechazada(client, session):
    await _make_cliente(session, 4)
    producto = await _make_producto(session)
    pedido = await _create_pedido(client, 4, producto.id, 10)
    pid = pedido["id"]

    await _avanzar_hasta_preparado(client, pid)
    resp = await client.patch(f"/costos/pedidos/{pid}/estado", json={"nuevo_estado": "LISTO_PARA_ENTREGA"})
    assert resp.status_code == 422

    remitos = (await client.get("/costos/remitos", params={"pedido_id": pid})).json()
    assert len(remitos) == 0

    pedido_after = (await client.get(f"/costos/pedidos/{pid}")).json()
    assert pedido_after["estado"] == "PREPARADO"


async def test_pedido_sucursal_genera_remito_transferencia(client, session):
    fabrica_id = await _make_sucursal(client, "Fábrica", tipo="FABRICA")
    sucursal_id = await _make_sucursal(client, "Centro")
    producto = await _make_producto(session)
    pedido = await _create_pedido_sucursal(client, sucursal_id, producto.id, 10)
    pid = pedido["id"]
    detalle_id = pedido["detalles"][0]["id"]

    await client.patch(f"/costos/pedidos/{pid}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 10}]})
    await _avanzar_hasta_preparado(client, pid)
    resp = await client.patch(f"/costos/pedidos/{pid}/estado", json={"nuevo_estado": "LISTO_PARA_ENTREGA"})
    assert resp.status_code == 200, resp.json()

    remitos = (await client.get("/costos/remitos", params={"pedido_id": pid})).json()
    assert len(remitos) == 1
    remito = remitos[0]
    assert remito["tipo"] == "TRANSFERENCIA"
    assert remito["origen_sucursal_id"] == fabrica_id
    assert remito["destino_sucursal_id"] == sucursal_id
    assert remito["detalles"][0]["cantidad"] == 10


async def test_pedido_sucursal_sin_fabrica_es_rechazado(client, session):
    sucursal_id = await _make_sucursal(client, "Centro")
    producto = await _make_producto(session)
    pedido = await _create_pedido_sucursal(client, sucursal_id, producto.id, 10)
    pid = pedido["id"]
    detalle_id = pedido["detalles"][0]["id"]

    await client.patch(f"/costos/pedidos/{pid}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 10}]})
    await _avanzar_hasta_preparado(client, pid)
    resp = await client.patch(f"/costos/pedidos/{pid}/estado", json={"nuevo_estado": "LISTO_PARA_ENTREGA"})
    assert resp.status_code == 422

    remitos = (await client.get("/costos/remitos", params={"pedido_id": pid})).json()
    assert len(remitos) == 0
