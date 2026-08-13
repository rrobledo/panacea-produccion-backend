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


async def _create_pedido(client, cliente_id, detalles=None):
    now = datetime.now(timezone.utc)
    resp = await client.post(
        "/costos/pedidos",
        json={
            "cliente_id": cliente_id,
            "vendedor": "Ana",
            "fecha_entrega": now.isoformat(),
            "detalles": detalles or [],
        },
    )
    return resp.json()


async def test_crear_pedido_con_detalle(client, session):
    await _make_cliente(session, 1)
    producto = await _make_producto(session)

    pedido = await _create_pedido(client, 1, detalles=[{"producto_id": producto.id, "cantidad_pedida": 10}])
    assert pedido["estado"] == "PENDIENTE"
    assert len(pedido["detalles"]) == 1
    assert pedido["detalles"][0]["cantidad_pedida"] == 10
    assert pedido["detalles"][0]["cantidad_entregada"] == 0


async def test_transicion_valida_de_un_paso(client, session):
    await _make_cliente(session, 2)
    pedido = await _create_pedido(client, 2)

    resp = await client.patch(f"/costos/pedidos/{pedido['id']}/estado", json={"nuevo_estado": "EN_PREPARACION"})
    assert resp.status_code == 200
    assert resp.json()["estado"] == "EN_PREPARACION"
    assert resp.json()["fecha_en_preparacion"] is not None


async def test_transicion_salteando_paso_es_rechazada(client, session):
    await _make_cliente(session, 3)
    pedido = await _create_pedido(client, 3)

    resp = await client.patch(f"/costos/pedidos/{pedido['id']}/estado", json={"nuevo_estado": "LISTO_PARA_ENTREGA"})
    assert resp.status_code == 422


async def test_transicion_desde_entregado_es_rechazada(client, session):
    await _make_cliente(session, 4)
    producto = await _make_producto(session)
    pedido = await _create_pedido(client, 4, detalles=[{"producto_id": producto.id, "cantidad_pedida": 5}])
    pid = pedido["id"]
    detalle_id = pedido["detalles"][0]["id"]

    await client.patch(f"/costos/pedidos/{pid}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 5}]})
    for estado in ["EN_PREPARACION", "PREPARADO", "LISTO_PARA_ENTREGA", "ENTREGADO"]:
        resp = await client.patch(f"/costos/pedidos/{pid}/estado", json={"nuevo_estado": estado})
        assert resp.status_code == 200, resp.json()

    body = resp.json()
    assert body["fecha_en_preparacion"] is not None
    assert body["fecha_preparado"] is not None
    assert body["fecha_listo_para_entrega"] is not None
    assert body["fecha_entregado"] is not None

    resp = await client.patch(f"/costos/pedidos/{pid}/estado", json={"nuevo_estado": "PENDIENTE"})
    assert resp.status_code == 422


async def test_registrar_entrega_parcial(client, session):
    await _make_cliente(session, 5)
    producto = await _make_producto(session)
    pedido = await _create_pedido(client, 5, detalles=[{"producto_id": producto.id, "cantidad_pedida": 10}])
    detalle_id = pedido["detalles"][0]["id"]

    resp = await client.patch(
        f"/costos/pedidos/{pedido['id']}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 6}]}
    )
    assert resp.status_code == 200
    assert resp.json()["detalles"][0]["cantidad_entregada"] == 6


async def test_entrega_mayor_a_lo_pedido_es_rechazada(client, session):
    await _make_cliente(session, 6)
    producto = await _make_producto(session)
    pedido = await _create_pedido(client, 6, detalles=[{"producto_id": producto.id, "cantidad_pedida": 10}])
    detalle_id = pedido["detalles"][0]["id"]

    resp = await client.patch(
        f"/costos/pedidos/{pedido['id']}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 11}]}
    )
    assert resp.status_code == 422


async def test_entrega_menor_a_lo_ya_entregado_es_rechazada(client, session):
    await _make_cliente(session, 7)
    producto = await _make_producto(session)
    pedido = await _create_pedido(client, 7, detalles=[{"producto_id": producto.id, "cantidad_pedida": 10}])
    detalle_id = pedido["detalles"][0]["id"]
    await client.patch(
        f"/costos/pedidos/{pedido['id']}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 6}]}
    )

    resp = await client.patch(
        f"/costos/pedidos/{pedido['id']}/entrega", json={"lineas": [{"detalle_id": detalle_id, "cantidad_entregada": 3}]}
    )
    assert resp.status_code == 422


async def test_editar_pedido_pendiente(client, session):
    await _make_cliente(session, 8)
    pedido = await _create_pedido(client, 8)

    resp = await client.put(f"/costos/pedidos/{pedido['id']}", json={"vendedor": "Beto"})
    assert resp.status_code == 200
    assert resp.json()["vendedor"] == "Beto"


async def test_editar_pedido_en_preparacion_es_rechazado(client, session):
    await _make_cliente(session, 9)
    pedido = await _create_pedido(client, 9)
    await client.patch(f"/costos/pedidos/{pedido['id']}/estado", json={"nuevo_estado": "EN_PREPARACION"})

    resp = await client.put(f"/costos/pedidos/{pedido['id']}", json={"vendedor": "Beto"})
    assert resp.status_code == 422


async def test_cancelar_pedido_pendiente(client, session):
    await _make_cliente(session, 10)
    pedido = await _create_pedido(client, 10)

    resp = await client.patch(f"/costos/pedidos/{pedido['id']}/estado", json={"nuevo_estado": "CANCELADO"})
    assert resp.status_code == 200
    assert resp.json()["estado"] == "CANCELADO"
    assert resp.json()["fecha_cancelado"] is not None
