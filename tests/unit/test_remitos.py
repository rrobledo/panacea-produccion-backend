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


async def _make_sucursal(client, nombre, tipo="SUCURSAL"):
    resp = await client.post("/costos/sucursales", json={"nombre": nombre, "tipo": tipo})
    return resp.json()["id"]


async def test_create_remito_venta_sin_pedido(client, session):
    await _make_cliente(session, 1)
    producto = await _make_producto(session)

    resp = await client.post(
        "/costos/remitos",
        json={
            "tipo": "VENTA",
            "cliente_id": 1,
            "vendedor": "Ana",
            "detalles": [{"producto_id": producto.id, "cantidad": 5}],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["pedido_id"] is None
    assert body["estado"] == "LISTO"
    assert body["fecha_listo"] is not None
    assert body["detalles"][0]["cantidad"] == 5


async def test_create_remito_transferencia(client, session):
    origen = await _make_sucursal(client, "Centro")
    destino = await _make_sucursal(client, "Fábrica", tipo="FABRICA")
    producto = await _make_producto(session)

    resp = await client.post(
        "/costos/remitos",
        json={
            "tipo": "TRANSFERENCIA",
            "origen_sucursal_id": origen,
            "destino_sucursal_id": destino,
            "detalles": [{"producto_id": producto.id, "cantidad": 3}],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["cliente_id"] is None
    assert body["pedido_id"] is None
    assert body["origen_sucursal"]["nombre"] == "Centro"
    assert body["destino_sucursal"]["tipo"] == "FABRICA"


async def test_transferencia_con_origen_igual_a_destino_es_rechazada(client, session):
    origen = await _make_sucursal(client, "Centro")

    resp = await client.post(
        "/costos/remitos",
        json={"tipo": "TRANSFERENCIA", "origen_sucursal_id": origen, "destino_sucursal_id": origen, "detalles": []},
    )
    assert resp.status_code == 400


async def test_venta_con_sucursal_es_rechazada(client, session):
    await _make_cliente(session, 2)
    origen = await _make_sucursal(client, "Centro")

    resp = await client.post(
        "/costos/remitos",
        json={"tipo": "VENTA", "cliente_id": 2, "origen_sucursal_id": origen, "detalles": []},
    )
    assert resp.status_code == 400


async def test_transferencia_con_cliente_id_es_rechazada(client, session):
    await _make_cliente(session, 3)
    origen = await _make_sucursal(client, "Centro")
    destino = await _make_sucursal(client, "Norte")

    resp = await client.post(
        "/costos/remitos",
        json={
            "tipo": "TRANSFERENCIA",
            "cliente_id": 3,
            "origen_sucursal_id": origen,
            "destino_sucursal_id": destino,
            "detalles": [],
        },
    )
    assert resp.status_code == 400


async def test_venta_sin_cliente_id_es_rechazada(client, session):
    resp = await client.post("/costos/remitos", json={"tipo": "VENTA", "detalles": []})
    assert resp.status_code == 400


async def test_transiciones_de_estado_remito(client, session):
    await _make_cliente(session, 4)
    resp = await client.post("/costos/remitos", json={"tipo": "VENTA", "cliente_id": 4, "detalles": []})
    remito_id = resp.json()["id"]

    for next_estado in ["EN_TRANSITO", "RECIBIDO"]:
        resp = await client.patch(f"/costos/remitos/{remito_id}/estado", json={"nuevo_estado": next_estado})
        assert resp.status_code == 200, resp.json()
        assert resp.json()["estado"] == next_estado


async def test_transicion_salteando_paso_es_rechazada(client, session):
    await _make_cliente(session, 5)
    resp = await client.post("/costos/remitos", json={"tipo": "VENTA", "cliente_id": 5, "detalles": []})
    remito_id = resp.json()["id"]

    resp = await client.patch(f"/costos/remitos/{remito_id}/estado", json={"nuevo_estado": "RECIBIDO"})
    assert resp.status_code == 422


async def test_transicion_retrocediendo_es_rechazada(client, session):
    await _make_cliente(session, 6)
    resp = await client.post("/costos/remitos", json={"tipo": "VENTA", "cliente_id": 6, "detalles": []})
    remito_id = resp.json()["id"]
    await client.patch(f"/costos/remitos/{remito_id}/estado", json={"nuevo_estado": "EN_TRANSITO"})

    resp = await client.patch(f"/costos/remitos/{remito_id}/estado", json={"nuevo_estado": "LISTO"})
    assert resp.status_code == 422


async def test_editar_remito_listo(client, session):
    await _make_cliente(session, 7)
    resp = await client.post("/costos/remitos", json={"tipo": "VENTA", "cliente_id": 7, "detalles": []})
    remito_id = resp.json()["id"]

    resp = await client.put(f"/costos/remitos/{remito_id}", json={"observaciones": "actualizado"})
    assert resp.status_code == 200
    assert resp.json()["observaciones"] == "actualizado"


async def test_borrar_remito_no_listo_es_rechazado(client, session):
    await _make_cliente(session, 8)
    resp = await client.post("/costos/remitos", json={"tipo": "VENTA", "cliente_id": 8, "detalles": []})
    remito_id = resp.json()["id"]
    await client.patch(f"/costos/remitos/{remito_id}/estado", json={"nuevo_estado": "EN_TRANSITO"})

    resp = await client.delete(f"/costos/remitos/{remito_id}")
    assert resp.status_code == 422

    resp = await client.get(f"/costos/remitos/{remito_id}")
    assert resp.status_code == 200


async def test_filtrar_por_tipo_y_destino_sucursal(client, session):
    await _make_cliente(session, 9)
    origen = await _make_sucursal(client, "Centro")
    destino = await _make_sucursal(client, "Fábrica", tipo="FABRICA")
    await client.post("/costos/remitos", json={"tipo": "VENTA", "cliente_id": 9, "detalles": []})
    await client.post(
        "/costos/remitos",
        json={"tipo": "TRANSFERENCIA", "origen_sucursal_id": origen, "destino_sucursal_id": destino, "detalles": []},
    )

    resp = await client.get("/costos/remitos", params={"tipo": "TRANSFERENCIA", "destino_sucursal_id": destino})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["tipo"] == "TRANSFERENCIA"


async def test_fecha_carga_now(client, session):
    before = datetime.now(timezone.utc)
    await _make_cliente(session, 10)
    resp = await client.post("/costos/remitos", json={"tipo": "VENTA", "cliente_id": 10, "detalles": []})
    fecha_carga = datetime.fromisoformat(resp.json()["fecha_carga"].replace("Z", "+00:00"))
    assert fecha_carga >= before


async def test_editar_remito_preserva_fecha_creacion_de_items_existentes(client, session):
    # update_remito hace merge por producto_id en vez de borrar y recrear
    # todas las filas de detalle, para poder distinguir items agregados al
    # crear el remito de los agregados despues en una edicion.
    await _make_cliente(session, 41)
    p1 = await _make_producto(session, codigo="P41A")
    p2 = await _make_producto(session, codigo="P41B")

    created = await client.post(
        "/costos/remitos",
        json={
            "tipo": "VENTA",
            "cliente_id": 41,
            "vendedor": "Ana",
            "detalles": [{"producto_id": p1.id, "cantidad": 5}],
        },
    )
    remito = created.json()
    detalle_id_original = remito["detalles"][0]["id"]
    fecha_creacion_original = remito["detalles"][0]["fecha_creacion"]

    resp = await client.put(
        f"/costos/remitos/{remito['id']}",
        json={
            "detalles": [
                {"producto_id": p1.id, "cantidad": 9},
                {"producto_id": p2.id, "cantidad": 2},
            ]
        },
    )
    assert resp.status_code == 200
    detalles = {d["producto_id"]: d for d in resp.json()["detalles"]}

    original = detalles[p1.id]
    assert original["id"] == detalle_id_original
    assert original["cantidad"] == 9
    assert original["fecha_creacion"] == fecha_creacion_original

    nuevo = detalles[p2.id]
    assert nuevo["id"] != detalle_id_original
