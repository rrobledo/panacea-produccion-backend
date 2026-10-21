"""scripts/migrate_remitos_to_pedidos_unificados.sql — ver
openspec/changes/unificar-pedidos-y-remitos/design.md, Decision 8."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.models.productos import Productos

SCRIPT = "migrate_remitos_to_pedidos_unificados.sql"

T0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


async def _exec(session, sql, **params):
    return await session.execute(text(sql), params)


async def _scalar(session, sql, **params):
    return (await session.execute(text(sql), params)).scalar_one()


async def _make_producto(session, codigo, nombre):
    producto = Productos(codigo=codigo, nombre=nombre, utilidad=10, precio_actual=100, lote_produccion=10)
    session.add(producto)
    await session.flush()
    return producto.id


async def _sucursal(session, nombre, tipo="SUCURSAL"):
    return await _scalar(
        session, "INSERT INTO sucursales_sucursal (nombre, tipo) VALUES (:n, :t) RETURNING id", n=nombre, t=tipo
    )


async def _pedido(session, **cols):
    cols = {"tipo": "CLIENTE", "vendedor": "Ana", "estado": "ENTREGADO", "fecha_carga": T0, "fecha_entrega": T0} | cols
    names = ", ".join(cols)
    values = ", ".join(f":{k}" for k in cols)
    return await _scalar(session, f"INSERT INTO pedidos_pedido ({names}) VALUES ({values}) RETURNING id", **cols)


async def _pedido_detalle(session, pedido_id, producto_id, pedida, entregada, remitida):
    await _exec(
        session,
        "INSERT INTO pedidos_pedido_detalle (pedido_id, producto_id, cantidad_pedida, cantidad_entregada, cantidad_remitida)"
        " VALUES (:p, :pr, :pe, :en, :re)",
        p=pedido_id, pr=producto_id, pe=pedida, en=entregada, re=remitida,
    )


async def _remito(session, lineas, **cols):
    cols = {"tipo": "VENTA", "fecha_carga": T0} | cols
    names = ", ".join(cols)
    values = ", ".join(f":{k}" for k in cols)
    remito_id = await _scalar(session, f"INSERT INTO remitos_remito ({names}) VALUES ({values}) RETURNING id", **cols)
    for producto_id, cantidad, fecha_creacion in lineas:
        await _exec(
            session,
            "INSERT INTO remitos_remito_detalle (remito_id, producto_id, cantidad, fecha_creacion)"
            " VALUES (:r, :p, :c, :f)",
            r=remito_id, p=producto_id, c=cantidad, f=fecha_creacion,
        )
    return remito_id


async def _envio_de(session, remito_id):
    row = (
        await _exec(
            session,
            "SELECT p.* FROM pedidos_pedido p JOIN pedidos_remito_legacy l ON l.pedido_id = p.id"
            " WHERE l.remito_legacy_id = :r",
            r=remito_id,
        )
    ).mappings().one()
    return dict(row)


async def _lineas(session, pedido_id):
    rows = await _exec(
        session,
        "SELECT producto_id, cantidad_pedida, cantidad_entregada, fecha_creacion FROM pedidos_pedido_detalle"
        " WHERE pedido_id = :p ORDER BY producto_id",
        p=pedido_id,
    )
    return [dict(r) for r in rows.mappings()]


async def test_migra_remitos_manuales_absorbe_generados_y_es_reejecutable(session, correr_script):
    await _exec(session, "INSERT INTO clientes (idcliente, nom1, nom2) VALUES (1, 'Juan', 'Garcia')")
    pan = await _make_producto(session, "P1", "Pan")
    facturas = await _make_producto(session, "P2", "Facturas")
    fabrica = await _sucursal(session, "Fábrica", "FABRICA")
    centro = await _sucursal(session, "Centro")
    norte = await _sucursal(session, "Norte")
    t1 = T0 + timedelta(hours=2)

    # Pedido con un remito generado en vivo (las cuatro fechas iguales).
    pedido_vivo = await _pedido(session, cliente_id=1)
    await _pedido_detalle(session, pedido_vivo, pan, 10, 6, 6)
    generado_vivo = await _remito(
        session, [(pan, 6, T0)], cliente_id=1, pedido_id=pedido_vivo,
        fecha_listo=T0, fecha_despacho=T0, fecha_recibido=T0,
    )

    # Pedido del backfill de costos_remitos (remito con fecha_listo NULL), facturado en el legacy.
    await _exec(
        session,
        "INSERT INTO costos_remitos (id, vendedor, fecha_carga, fecha_entrega, cliente_id, fecha_facturacion)"
        " VALUES (77, 'Ana', :t, :t, 1, :f)",
        t=T0, f=T0 + timedelta(days=3),
    )
    pedido_legacy = await _pedido(
        session, cliente_id=1, observaciones="[migrado de costos_remitos#77, estado_legacy=facturado] | nota"
    )
    await _pedido_detalle(session, pedido_legacy, pan, 2, 2, 2)
    generado_backfill = await _remito(
        session, [(pan, 2, T0)], cliente_id=1, pedido_id=pedido_legacy, fecha_despacho=T0, fecha_recibido=T0
    )

    # Pedido de sucursal sin origen y sin remito.
    pedido_sucursal = await _pedido(session, tipo="SUCURSAL", sucursal_id=centro, estado="PENDIENTE")

    # Remito manual VENTA sin pedido, RECIBIDO, con un producto repetido.
    manual_venta = await _remito(
        session, [(pan, 3, T0), (pan, 2, t1), (facturas, 1, t1)], cliente_id=1, vendedor="Luis",
        observaciones="urgente", fecha_listo=T0, fecha_despacho=t1, fecha_recibido=t1,
    )
    # Remito manual TRANSFERENCIA en tránsito.
    manual_transferencia = await _remito(
        session, [(facturas, 4, T0)], tipo="TRANSFERENCIA", origen_sucursal_id=centro,
        destino_sucursal_id=norte, fecha_listo=T0, fecha_despacho=t1,
    )
    # Remito manual VENTA cargado sobre un pedido (no generado: fecha_recibido distinta).
    manual_con_pedido = await _remito(
        session, [(facturas, 2, T0)], cliente_id=1, pedido_id=pedido_vivo,
        fecha_listo=T0, fecha_despacho=t1, fecha_recibido=t1,
    )
    await session.commit()

    await correr_script(SCRIPT)
    pedidos_tras_primera = await _scalar(session, "SELECT count(*) FROM pedidos_pedido")
    await correr_script(SCRIPT)

    # Re-ejecutable: nada se duplica.
    assert await _scalar(session, "SELECT count(*) FROM pedidos_pedido") == pedidos_tras_primera == 6
    assert await _scalar(session, "SELECT count(*) FROM pedidos_remito_legacy") == 5

    # Generados: absorbidos en su propio pedido.
    assert (await _envio_de(session, generado_vivo))["id"] == pedido_vivo
    assert (await _envio_de(session, generado_backfill))["id"] == pedido_legacy

    # Manual VENTA -> envío es_remito CLIENTE ENTREGADO con líneas agrupadas.
    venta = await _envio_de(session, manual_venta)
    assert venta["es_remito"] is True
    assert (venta["tipo"], venta["cliente_id"], venta["estado"]) == ("CLIENTE", 1, "ENTREGADO")
    assert venta["vendedor"] == "Luis"
    assert venta["fecha_entregado"] == t1
    assert venta["observaciones"] == f"[migrado de remitos_remito#{manual_venta}] | urgente"
    assert await _lineas(session, venta["id"]) == [
        {"producto_id": pan, "cantidad_pedida": 0, "cantidad_entregada": 5, "fecha_creacion": T0},
        {"producto_id": facturas, "cantidad_pedida": 0, "cantidad_entregada": 1, "fecha_creacion": t1},
    ]

    # Manual TRANSFERENCIA en tránsito -> SUCURSAL LISTO_PARA_ENTREGA con la nota del despacho.
    transferencia = await _envio_de(session, manual_transferencia)
    assert (transferencia["tipo"], transferencia["estado"]) == ("SUCURSAL", "LISTO_PARA_ENTREGA")
    assert (transferencia["origen_sucursal_id"], transferencia["sucursal_id"]) == (centro, norte)
    assert transferencia["cliente_id"] is None
    assert "[en tránsito desde 2026-09-01" in transferencia["observaciones"]

    # Manual con pedido -> envío propio que referencia el pedido en observaciones.
    con_pedido = await _envio_de(session, manual_con_pedido)
    assert con_pedido["es_remito"] is True
    assert f"[remito manual del pedido #{pedido_vivo}]" in con_pedido["observaciones"]

    # Origen por defecto desde la fábrica y facturación legacy.
    assert await _scalar(
        session, "SELECT origen_sucursal_id FROM pedidos_pedido WHERE id = :p", p=pedido_sucursal
    ) == fabrica
    legacy = (
        await _exec(session, "SELECT fecha_facturado, factura_referencia FROM pedidos_pedido WHERE id = :p", p=pedido_legacy)
    ).one()
    assert legacy == (T0 + timedelta(days=3), "LEGACY costos_remitos#77")
    assert await _scalar(
        session, "SELECT count(*) FROM pedidos_pedido WHERE fecha_facturado IS NOT NULL"
    ) == 1
