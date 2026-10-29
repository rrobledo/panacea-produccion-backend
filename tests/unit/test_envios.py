"""Envío unificado: remito directo, transferencias, facturación y filtros —
ver openspec/changes/unificar-pedidos-y-remitos/specs/envios/spec.md."""

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


async def _make_sucursal(client, nombre, tipo="SUCURSAL"):
    resp = await client.post("/costos/sucursales", json={"nombre": nombre, "tipo": tipo})
    return resp.json()["id"]


def _remito_payload(detalles, **overrides):
    payload = {
        "es_remito": True,
        "vendedor": "Ana",
        "fecha_entrega": datetime.now(timezone.utc).isoformat(),
        "detalles": detalles,
    }
    payload.update(overrides)
    return payload


async def _create_remito_cliente(client, cliente_id, producto_id, cantidad_entregada):
    resp = await client.post(
        "/costos/pedidos",
        json=_remito_payload(
            [{"producto_id": producto_id, "cantidad_pedida": 0, "cantidad_entregada": cantidad_entregada}],
            cliente_id=cliente_id,
        ),
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()


async def _pedido_entregado(client, cliente_id, producto_id):
    resp = await client.post(
        "/costos/pedidos",
        json={
            "cliente_id": cliente_id,
            "vendedor": "Ana",
            "fecha_entrega": datetime.now(timezone.utc).isoformat(),
            "detalles": [{"producto_id": producto_id, "cantidad_pedida": 5}],
        },
    )
    pedido = resp.json()
    await client.patch(
        f"/costos/pedidos/{pedido['id']}/entrega",
        json={"lineas": [{"detalle_id": pedido["detalles"][0]["id"], "cantidad_entregada": 5}]},
    )
    for estado in ["EN_PREPARACION", "PREPARADO", "LISTO_PARA_ENTREGA", "ENTREGADO"]:
        resp = await client.patch(f"/costos/pedidos/{pedido['id']}/estado", json={"nuevo_estado": estado})
        assert resp.status_code == 200, resp.json()
    return resp.json()


# ── Remito directo ──


async def test_remito_directo_nace_listo_para_entrega(client, session):
    await _make_cliente(session, 1)
    producto = await _make_producto(session)

    body = await _create_remito_cliente(client, 1, producto.id, 8)

    assert body["es_remito"] is True
    assert body["tipo"] == "CLIENTE"
    assert body["estado"] == "LISTO_PARA_ENTREGA"
    assert body["fecha_listo_para_entrega"] is not None
    assert body["fecha_facturado"] is None
    [linea] = body["detalles"]
    assert linea["cantidad_pedida"] == 0
    assert linea["cantidad_entregada"] == 8


async def test_remito_directo_con_cantidad_pedida_es_rechazado(client, session):
    await _make_cliente(session, 2)
    producto = await _make_producto(session)

    resp = await client.post(
        "/costos/pedidos",
        json=_remito_payload(
            [{"producto_id": producto.id, "cantidad_pedida": 3, "cantidad_entregada": 3}], cliente_id=2
        ),
    )
    assert resp.status_code == 400
    assert (await client.get("/costos/pedidos")).json() == []


async def test_remito_directo_sin_entregas_es_rechazado(client, session):
    await _make_cliente(session, 3)
    producto = await _make_producto(session)

    resp = await client.post(
        "/costos/pedidos",
        json=_remito_payload([{"producto_id": producto.id, "cantidad_pedida": 0, "cantidad_entregada": 0}], cliente_id=3),
    )
    assert resp.status_code == 400


async def test_remito_directo_avanza_solo_a_entregado(client, session):
    await _make_cliente(session, 4)
    producto = await _make_producto(session)
    remito = await _create_remito_cliente(client, 4, producto.id, 2)

    resp = await client.patch(f"/costos/pedidos/{remito['id']}/estado", json={"nuevo_estado": "PREPARADO"})
    assert resp.status_code == 422

    resp = await client.patch(f"/costos/pedidos/{remito['id']}/estado", json={"nuevo_estado": "ENTREGADO"})
    assert resp.status_code == 200, resp.json()
    assert resp.json()["fecha_entregado"] is not None


async def test_editar_remito_listo_actualiza_entregado_y_preserva_fecha_creacion(client, session):
    await _make_cliente(session, 5)
    pan = await _make_producto(session)
    facturas = await _make_producto(session, codigo="P2", nombre="Facturas")
    remito = await _create_remito_cliente(client, 5, pan.id, 4)
    fecha_original = remito["detalles"][0]["fecha_creacion"]

    resp = await client.put(
        f"/costos/pedidos/{remito['id']}",
        json={
            "detalles": [
                {"producto_id": pan.id, "cantidad_pedida": 0, "cantidad_entregada": 5},
                {"producto_id": facturas.id, "cantidad_pedida": 0, "cantidad_entregada": 2},
            ]
        },
    )
    assert resp.status_code == 200, resp.json()
    lineas = {d["producto_id"]: d for d in resp.json()["detalles"]}
    assert lineas[pan.id]["cantidad_entregada"] == 5
    assert lineas[pan.id]["fecha_creacion"] == fecha_original
    assert lineas[facturas.id]["cantidad_entregada"] == 2
    assert lineas[facturas.id]["cantidad_pedida"] == 0


async def test_editar_remito_con_cantidad_pedida_es_rechazado(client, session):
    await _make_cliente(session, 6)
    producto = await _make_producto(session)
    remito = await _create_remito_cliente(client, 6, producto.id, 4)

    resp = await client.put(
        f"/costos/pedidos/{remito['id']}",
        json={"detalles": [{"producto_id": producto.id, "cantidad_pedida": 1, "cantidad_entregada": 4}]},
    )
    assert resp.status_code == 422


async def test_editar_o_borrar_remito_entregado_es_rechazado(client, session):
    await _make_cliente(session, 7)
    producto = await _make_producto(session)
    remito = await _create_remito_cliente(client, 7, producto.id, 4)
    await client.patch(f"/costos/pedidos/{remito['id']}/estado", json={"nuevo_estado": "ENTREGADO"})

    resp = await client.put(f"/costos/pedidos/{remito['id']}", json={"observaciones": "x"})
    assert resp.status_code == 422
    resp = await client.delete(f"/costos/pedidos/{remito['id']}")
    assert resp.status_code == 422


async def test_borrar_remito_listo(client, session):
    await _make_cliente(session, 8)
    producto = await _make_producto(session)
    remito = await _create_remito_cliente(client, 8, producto.id, 4)

    resp = await client.delete(f"/costos/pedidos/{remito['id']}")
    assert resp.status_code == 204


# ── Transferencias entre sucursales ──


async def test_transferencia_con_origen_explicito(client, session):
    producto = await _make_producto(session)
    origen = await _make_sucursal(client, "Centro")
    destino = await _make_sucursal(client, "Norte")

    resp = await client.post(
        "/costos/pedidos",
        json=_remito_payload(
            [{"producto_id": producto.id, "cantidad_pedida": 0, "cantidad_entregada": 3}],
            tipo="SUCURSAL",
            origen_sucursal_id=origen,
            sucursal_id=destino,
        ),
    )
    assert resp.status_code == 201, resp.json()
    body = resp.json()
    assert body["origen_sucursal"]["nombre"] == "Centro"
    assert body["sucursal"]["nombre"] == "Norte"


async def test_transferencia_sin_fabrica_unica_es_rechazada(client, session):
    producto = await _make_producto(session)
    destino = await _make_sucursal(client, "Norte")

    resp = await client.post(
        "/costos/pedidos",
        json=_remito_payload(
            [{"producto_id": producto.id, "cantidad_pedida": 0, "cantidad_entregada": 3}],
            tipo="SUCURSAL",
            sucursal_id=destino,
        ),
    )
    assert resp.status_code == 422
    assert "FABRICA" in resp.json()["detail"]


async def test_transferencia_origen_igual_destino_es_rechazada(client, session):
    producto = await _make_producto(session)
    sucursal = await _make_sucursal(client, "Norte")

    resp = await client.post(
        "/costos/pedidos",
        json=_remito_payload(
            [{"producto_id": producto.id, "cantidad_pedida": 0, "cantidad_entregada": 3}],
            tipo="SUCURSAL",
            origen_sucursal_id=sucursal,
            sucursal_id=sucursal,
        ),
    )
    assert resp.status_code == 400


async def test_pedido_a_la_fabrica_sin_origen_es_rechazado(client, session):
    fabrica = await _make_sucursal(client, "Fábrica", tipo="FABRICA")

    resp = await client.post(
        "/costos/pedidos",
        json={
            "tipo": "SUCURSAL",
            "sucursal_id": fabrica,
            "vendedor": "Ana",
            "fecha_entrega": datetime.now(timezone.utc).isoformat(),
            "detalles": [],
        },
    )
    assert resp.status_code == 422


# ── Pedido: ya no genera remitos ──


async def test_pedido_sin_entregas_no_llega_a_listo_para_entrega(client, session):
    await _make_cliente(session, 9)
    producto = await _make_producto(session)
    resp = await client.post(
        "/costos/pedidos",
        json={
            "cliente_id": 9,
            "vendedor": "Ana",
            "fecha_entrega": datetime.now(timezone.utc).isoformat(),
            "detalles": [{"producto_id": producto.id, "cantidad_pedida": 5}],
        },
    )
    pid = resp.json()["id"]
    for estado in ["EN_PREPARACION", "PREPARADO"]:
        await client.patch(f"/costos/pedidos/{pid}/estado", json={"nuevo_estado": estado})

    resp = await client.patch(f"/costos/pedidos/{pid}/estado", json={"nuevo_estado": "LISTO_PARA_ENTREGA"})
    assert resp.status_code == 422
    assert "entrega" in resp.json()["detail"]


async def test_pedido_entregado_no_crea_otro_envio(client, session):
    await _make_cliente(session, 10)
    producto = await _make_producto(session)

    pedido = await _pedido_entregado(client, 10, producto.id)

    envios = (await client.get("/costos/pedidos")).json()
    assert [e["id"] for e in envios] == [pedido["id"]]
    assert pedido["es_remito"] is False


async def test_api_de_remitos_ya_no_existe(client, session):
    resp = await client.get("/costos/remitos")
    assert resp.status_code == 404


# ── Facturación ──


async def test_facturar_envio_entregado(client, session):
    await _make_cliente(session, 11)
    producto = await _make_producto(session)
    pedido = await _pedido_entregado(client, 11, producto.id)

    resp = await client.patch(
        f"/costos/pedidos/{pedido['id']}/facturacion",
        json={"fecha_facturado": "2026-10-20T00:00:00Z", "factura_referencia": " A-0001-00001234 "},
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["fecha_facturado"].startswith("2026-10-20")
    assert body["factura_referencia"] == "A-0001-00001234"

    facturados = (await client.get("/costos/pedidos", params={"facturado": True})).json()
    assert [e["id"] for e in facturados] == [pedido["id"]]
    assert (await client.get("/costos/pedidos", params={"facturado": False})).json() == []


async def test_facturar_sin_referencia_es_rechazado(client, session):
    await _make_cliente(session, 12)
    producto = await _make_producto(session)
    pedido = await _pedido_entregado(client, 12, producto.id)

    resp = await client.patch(
        f"/costos/pedidos/{pedido['id']}/facturacion",
        json={"fecha_facturado": "2026-10-20T00:00:00Z", "factura_referencia": "  "},
    )
    assert resp.status_code == 400


async def test_facturar_pedido_pendiente_es_rechazado(client, session):
    await _make_cliente(session, 13)
    producto = await _make_producto(session)
    resp = await client.post(
        "/costos/pedidos",
        json={
            "cliente_id": 13,
            "vendedor": "Ana",
            "fecha_entrega": datetime.now(timezone.utc).isoformat(),
            "detalles": [{"producto_id": producto.id, "cantidad_pedida": 5}],
        },
    )
    resp = await client.patch(
        f"/costos/pedidos/{resp.json()['id']}/facturacion",
        json={"fecha_facturado": "2026-10-20T00:00:00Z", "factura_referencia": "A-1"},
    )
    assert resp.status_code == 422


async def test_desmarcar_facturacion(client, session):
    await _make_cliente(session, 14)
    producto = await _make_producto(session)
    remito = await _create_remito_cliente(client, 14, producto.id, 3)
    url = f"/costos/pedidos/{remito['id']}/facturacion"
    await client.patch(url, json={"fecha_facturado": "2026-10-20T00:00:00Z", "factura_referencia": "A-1"})

    resp = await client.patch(url, json={"fecha_facturado": None, "factura_referencia": None})
    assert resp.status_code == 200
    assert resp.json()["fecha_facturado"] is None
    assert resp.json()["factura_referencia"] is None


async def test_envio_facturado_no_se_cancela_edita_ni_registra_entrega(client, session):
    await _make_cliente(session, 15)
    producto = await _make_producto(session)
    remito = await _create_remito_cliente(client, 15, producto.id, 3)
    rid = remito["id"]
    await client.patch(
        f"/costos/pedidos/{rid}/facturacion", json={"fecha_facturado": "2026-10-20T00:00:00Z", "factura_referencia": "A-1"}
    )

    resp = await client.patch(f"/costos/pedidos/{rid}/estado", json={"nuevo_estado": "CANCELADO"})
    assert resp.status_code == 422
    resp = await client.put(f"/costos/pedidos/{rid}", json={"observaciones": "x"})
    assert resp.status_code == 422
    resp = await client.patch(
        f"/costos/pedidos/{rid}/entrega",
        json={"lineas": [{"detalle_id": remito["detalles"][0]["id"], "cantidad_entregada": 4}]},
    )
    assert resp.status_code == 422


# ── Listado y reportes ──


async def test_listar_solo_remitos(client, session):
    await _make_cliente(session, 16)
    producto = await _make_producto(session)
    remito = await _create_remito_cliente(client, 16, producto.id, 3)
    await _pedido_entregado(client, 16, producto.id)

    remitos = (await client.get("/costos/pedidos", params={"es_remito": True})).json()
    assert [e["id"] for e in remitos] == [remito["id"]]


async def test_buscar_por_remito_legacy_id(client, session):
    await _make_cliente(session, 17)
    producto = await _make_producto(session)
    remito = await _create_remito_cliente(client, 17, producto.id, 3)
    await session.execute(
        text("INSERT INTO pedidos_remito_legacy (remito_legacy_id, pedido_id) VALUES (345, :pid)"),
        {"pid": remito["id"]},
    )
    await session.commit()

    encontrados = (await client.get("/costos/pedidos", params={"remito_legacy_id": 345})).json()
    assert [e["id"] for e in encontrados] == [remito["id"]]
    assert encontrados[0]["remitos_legacy_ids"] == [345]
    assert (await client.get("/costos/pedidos", params={"remito_legacy_id": 999})).json() == []


async def test_reportes_de_pendientes_excluyen_remitos(client, session):
    await _make_cliente(session, 18)
    producto = await _make_producto(session)
    await _create_remito_cliente(client, 18, producto.id, 3)
    hoy = datetime.now(timezone.utc)
    desde = (hoy - timedelta(days=1)).date().isoformat()
    hasta = (hoy + timedelta(days=1)).date().isoformat()

    assert (await client.get("/costos/pedidos-reportes/pendientes-entrega")).json() == []
    assert (await client.get("/costos/pedidos-reportes/pendientes-por-dia")).json() == []
    resp = await client.get(
        "/costos/pedidos-reportes/productos-pendientes-por-dia", params={"fecha_desde": desde, "fecha_hasta": hasta}
    )
    assert resp.json() == []


async def test_listar_como_remito_incluye_pedidos_que_pasaron_a_remito(client, session):
    await _make_cliente(session, 19)
    producto = await _make_producto(session)
    remito = await _create_remito_cliente(client, 19, producto.id, 3)
    entregado = await _pedido_entregado(client, 19, producto.id)
    pendiente = (
        await client.post(
            "/costos/pedidos",
            json={
                "cliente_id": 19,
                "vendedor": "Ana",
                "fecha_entrega": datetime.now(timezone.utc).isoformat(),
                "detalles": [{"producto_id": producto.id, "cantidad_pedida": 2}],
            },
        )
    ).json()

    como_remito = (await client.get("/costos/pedidos", params={"como_remito": True})).json()
    assert {e["id"] for e in como_remito} == {remito["id"], entregado["id"]}
    sin_remito = (await client.get("/costos/pedidos", params={"como_remito": False})).json()
    assert [e["id"] for e in sin_remito] == [pendiente["id"]]
