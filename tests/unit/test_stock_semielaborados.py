"""F2b de masa-procesos-y-maquinaria: el ledger cubre artículos producidos.

Ver openspec/changes/masa-procesos-y-maquinaria/{design.md D4 y D5,
specs/stock/spec.md, tasks.md 3.1-3.6} en el repo `panacea-produccion`.
"""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.insumos import Insumos
from app.models.ordenes_produccion import OrdenProduccion
from app.models.productos import Costos, Productos
from app.models.programacion import Programacion
from app.models.stock_movimiento import StockMovimiento
from app.models.ubicacion import Ubicacion
from app.services import stock_service

FECHA = date(2026, 8, 25)


async def _make_producto(session, **overrides):
    defaults = dict(
        codigo="S1", categoria="PANADERIA", nombre="Masa", utilidad=30, precio_actual=1000,
        unidad_medida="GR", lote_produccion=162, tiempo_produccion=2, responsable="Panaderia",
        is_producto=False, habilitado=True, prioridad=10,
        naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False,
    )
    defaults.update(overrides)
    producto = Productos(**defaults)
    session.add(producto)
    await session.commit()
    await session.refresh(producto)
    return producto


async def _make_insumo(session, **overrides):
    defaults = dict(nombre="Harina", unidad_medida="KG", cantidad=100000, precio=1000)
    defaults.update(overrides)
    insumo = Insumos(**defaults)
    session.add(insumo)
    await session.commit()
    await session.refresh(insumo)
    return insumo


async def _make_ubicacion(session):
    ubicacion = Ubicacion(nombre="Cámara")
    session.add(ubicacion)
    await session.commit()
    await session.refresh(ubicacion)
    return ubicacion


async def _make_orden(session, codigo="260101-01", estado="EN_PRODUCCION"):
    orden = OrdenProduccion(
        codigo=codigo, fecha_fabricacion=FECHA, responsable="Panaderia", estado=estado,
        fecha_creacion=datetime.now(timezone.utc),
    )
    session.add(orden)
    await session.commit()
    await session.refresh(orden)
    return orden


# ── 3.1 · un movimiento es de un artículo, y son dos tablas ─────────────────

async def test_un_movimiento_no_puede_ser_de_insumo_y_producto_a_la_vez(session):
    harina = await _make_insumo(session)
    masa = await _make_producto(session)

    session.add(StockMovimiento(
        insumo_id=harina.id, producto_id=masa.id, tipo="AJUSTE", cantidad=1,
        fecha=datetime.now(timezone.utc),
    ))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_un_movimiento_sin_articulo_es_rechazado(session):
    session.add(StockMovimiento(tipo="AJUSTE", cantidad=1, fecha=datetime.now(timezone.utc)))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


# ── 3.2 · finalizar una orden deja la masa con saldo ────────────────────────

async def test_finalizar_registra_produccion_del_semielaborado(client, session):
    harina = await _make_insumo(session)
    ubicacion = await _make_ubicacion(session)
    masa = await _make_producto(session, codigo="SM1", nombre="Masa de francés")
    session.add(Costos(producto_id=masa.id, insumo_id=harina.id, cantidad=100))
    session.add(Programacion(
        fecha=FECHA, producto_id=masa.id, producto_nombre=masa.nombre,
        responsable="Panaderia", plan=162, prod=None,
    ))
    await session.commit()

    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    orden = (await session.execute(select(OrdenProduccion))).scalars().one()
    await client.post(f"/costos/ordenes-produccion/{orden.id}/iniciar")

    response = await client.post(
        f"/costos/ordenes-produccion/{orden.id}/finalizar",
        json={"lineas": [{
            "producto_id": masa.id, "cantidad_fabricada": 162, "ubicacion_id": ubicacion.id,
            "cantidad_desperdicio": 0, "ubicacion_desperdicio_id": None, "motivo_desperdicio": None,
        }]},
    )
    assert response.status_code == 200

    assert await stock_service.disponible_de_articulo(session, masa.id) == 162
    produccion = (
        await session.execute(select(StockMovimiento).where(StockMovimiento.tipo == "PRODUCCION"))
    ).scalars().one()
    assert (produccion.producto_id, produccion.orden_id) == (masa.id, orden.id)


async def test_el_desperdicio_no_entra_al_stock(client, session):
    harina = await _make_insumo(session)
    ubicacion = await _make_ubicacion(session)
    masa = await _make_producto(session, codigo="SM2", nombre="Masa")
    session.add(Costos(producto_id=masa.id, insumo_id=harina.id, cantidad=100))
    session.add(Programacion(
        fecha=FECHA, producto_id=masa.id, producto_nombre=masa.nombre,
        responsable="Panaderia", plan=162, prod=None,
    ))
    await session.commit()

    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    orden = (await session.execute(select(OrdenProduccion))).scalars().one()
    await client.post(f"/costos/ordenes-produccion/{orden.id}/iniciar")
    await client.post(
        f"/costos/ordenes-produccion/{orden.id}/finalizar",
        json={"lineas": [{
            "producto_id": masa.id, "cantidad_fabricada": 150, "ubicacion_id": ubicacion.id,
            "cantidad_desperdicio": 12, "ubicacion_desperdicio_id": ubicacion.id,
            "motivo_desperdicio": "Masa pasada",
        }]},
    )

    # Lo tirado no está disponible para consumir.
    assert await stock_service.disponible_de_articulo(session, masa.id) == 150


async def test_cantidad_fabricada_cero_no_deja_movimiento(client, session):
    harina = await _make_insumo(session)
    ubicacion = await _make_ubicacion(session)
    masa = await _make_producto(session, codigo="SM3", nombre="Masa")
    session.add(Costos(producto_id=masa.id, insumo_id=harina.id, cantidad=100))
    session.add(Programacion(
        fecha=FECHA, producto_id=masa.id, producto_nombre=masa.nombre,
        responsable="Panaderia", plan=162, prod=None,
    ))
    await session.commit()

    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    orden = (await session.execute(select(OrdenProduccion))).scalars().one()
    await client.post(f"/costos/ordenes-produccion/{orden.id}/iniciar")
    await client.post(
        f"/costos/ordenes-produccion/{orden.id}/finalizar",
        json={"lineas": [{
            "producto_id": masa.id, "cantidad_fabricada": 0, "ubicacion_id": ubicacion.id,
            "cantidad_desperdicio": 0, "ubicacion_desperdicio_id": None, "motivo_desperdicio": None,
        }]},
    )

    producciones = (
        await session.execute(select(StockMovimiento).where(StockMovimiento.tipo == "PRODUCCION"))
    ).scalars().all()
    assert producciones == []


# ── 3.3 y 3.6 · consumir el sobrante ────────────────────────────────────────

async def test_producir_162_y_consumir_47_deja_115(session):
    masa = await _make_producto(session, codigo="SC1", nombre="Masa de francés")
    orden_uno = await _make_orden(session, codigo="260101-01")
    orden_dos = await _make_orden(session, codigo="260101-02")

    session.add(stock_service.crear_produccion(masa.id, 162, orden_uno.codigo, orden_uno.id))
    await session.commit()

    await stock_service.consumir_articulo(session, masa.id, 47, orden_dos.codigo, orden_dos.id)
    await session.commit()

    assert await stock_service.disponible_de_articulo(session, masa.id) == 115

    movimientos = await stock_service.list_movimientos_articulo(session, masa.id)
    assert sorted(m.tipo for m in movimientos) == ["CONSUMO_INTERNO", "PRODUCCION"]
    # Cada movimiento se puede rastrear hasta la orden que lo causó.
    assert {m.orden_id for m in movimientos} == {orden_uno.id, orden_dos.id}


async def test_no_se_puede_consumir_mas_de_lo_que_hay(session):
    masa = await _make_producto(session, codigo="SC2", nombre="Masa")
    orden = await _make_orden(session)
    session.add(stock_service.crear_produccion(masa.id, 10, orden.codigo, orden.id))
    await session.commit()

    with pytest.raises(Exception) as excinfo:
        await stock_service.consumir_articulo(session, masa.id, 11, orden.codigo, orden.id)

    assert "stock suficiente" in str(excinfo.value)


async def test_borrar_la_orden_se_lleva_sus_movimientos_de_articulo(session):
    masa = await _make_producto(session, codigo="SC3", nombre="Masa")
    orden = await _make_orden(session, estado="ASIGNADA")
    session.add(stock_service.crear_produccion(masa.id, 50, orden.codigo, orden.id))
    await session.commit()

    await session.delete(orden)
    await session.commit()

    assert (await session.execute(select(StockMovimiento))).scalars().all() == []


# ── 3.4 · el endpoint de stock ──────────────────────────────────────────────

async def test_listado_de_stock_de_semielaborados(client, session):
    masa = await _make_producto(session, codigo="SE1", nombre="Masa de chip")
    terminado = await _make_producto(
        session, codigo="SE2", nombre="Pebete", is_producto=True,
        naturaleza="TERMINADO", unidad_base="UN", vendible=True,
    )
    orden = await _make_orden(session)
    session.add(stock_service.crear_produccion(masa.id, 80, orden.codigo, orden.id))
    session.add(stock_service.crear_produccion(terminado.id, 200, orden.codigo, orden.id))
    await session.commit()

    response = await client.get("/costos/articulos")

    assert response.status_code == 200
    cuerpo = response.json()
    assert [a["producto_nombre"] for a in cuerpo] == ["Masa de chip"]
    assert cuerpo[0]["disponible"] == 80
    assert cuerpo[0]["unidad_base"] == "KG"


async def test_detalle_de_stock_trae_el_historial(client, session):
    masa = await _make_producto(session, codigo="SE3", nombre="Masa")
    orden = await _make_orden(session)
    session.add(stock_service.crear_produccion(masa.id, 100, orden.codigo, orden.id))
    await session.commit()
    await stock_service.consumir_articulo(session, masa.id, 30, orden.codigo, orden.id)
    await session.commit()

    response = await client.get(f"/costos/articulos/{masa.id}/movimientos")

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["disponible"] == 70
    assert len(cuerpo["movimientos"]) == 2
    assert {m["tipo"] for m in cuerpo["movimientos"]} == {"PRODUCCION", "CONSUMO_INTERNO"}


async def test_articulo_inexistente_da_404(client, session):
    response = await client.get("/costos/articulos/999999/movimientos")
    assert response.status_code == 404
