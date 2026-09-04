"""Generar lo pendiente de un día ya generado, y borrar órdenes."""
from datetime import date

from sqlalchemy import func, select

from app.models.insumos import Insumos
from app.models.ordenes_produccion import (
    OrdenProduccion,
    OrdenProduccionInsumoLinea,
    OrdenProduccionProductoLinea,
)
from app.models.productos import Costos, Productos
from app.models.programacion import Programacion
from app.models.stock_movimiento import StockMovimiento

FECHA = date(2026, 8, 25)


async def _producto(session, codigo, nombre, **overrides):
    defaults = dict(
        codigo=codigo, categoria="PANADERIA", nombre=nombre, utilidad=30, precio_actual=1000,
        unidad_medida="UN", lote_produccion=100, tiempo_produccion=2, responsable="Todos",
        is_producto=True, habilitado=True, prioridad=10,
    )
    defaults.update(overrides)
    p = Productos(**defaults)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


async def _insumo(session, nombre="Harina"):
    i = Insumos(nombre=nombre, unidad_medida="KG", cantidad=100000, precio=100)
    session.add(i)
    await session.commit()
    await session.refresh(i)
    return i


async def _receta(session, producto, insumo, cantidad=50):
    session.add(Costos(producto_id=producto.id, insumo_id=insumo.id, cantidad=cantidad))
    await session.commit()


async def _programar(session, producto, plan, responsable="Panaderia", fecha=FECHA):
    row = Programacion(fecha=fecha, producto_id=producto.id, producto_nombre=producto.nombre,
                       responsable=responsable, plan=plan, prod=None)
    session.add(row)
    await session.commit()
    return row


async def _generar(client, fecha=FECHA):
    r = await client.post("/costos/ordenes-produccion/generar", json={"fecha": fecha.isoformat()})
    assert r.status_code == 201, r.text
    return r.json()


async def _preview(client, fecha=FECHA):
    r = await client.post("/costos/ordenes-produccion/preview", json={"fecha": fecha.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


async def _count(session, model):
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


# ── Numeración de códigos ────────────────────────────────────────────────────

async def test_la_numeracion_continua_en_la_segunda_generacion(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "N1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    primera = await _generar(client)
    assert [o["codigo"] for o in primera] == ["260825-01"]

    # Un producto nuevo para la misma fecha
    torta = await _producto(session, "N2", "Torta")
    await _receta(session, torta, harina)
    await _programar(session, torta, 50, "Pasteleria")

    segunda = await _generar(client)
    assert [o["codigo"] for o in segunda] == ["260825-02"]

    todos = [o["codigo"] for o in (await client.get("/costos/ordenes-produccion")).json()]
    assert sorted(todos) == ["260825-01", "260825-02"]
    assert len(todos) == len(set(todos))  # sin duplicados


async def test_una_orden_cancelada_no_libera_su_numero(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "N3", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    await client.post(f"/costos/ordenes-produccion/{orden['id']}/cancelar")

    # Cancelada libera el producto -> vuelve a estar pendiente
    segunda = await _generar(client)
    assert [o["codigo"] for o in segunda] == ["260825-02"]  # no reusa el -01


# ── Pendientes ───────────────────────────────────────────────────────────────

async def test_producto_agregado_a_un_dia_generado_aparece_como_pendiente(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")
    await _generar(client)

    torta = await _producto(session, "P2", "Torta")
    await _receta(session, torta, harina)
    await _programar(session, torta, 50, "Pasteleria")

    cuerpo = await _preview(client)
    assert cuerpo["ordenes_existentes"] == 1
    assert [o["producto_base_nombre"] for o in cuerpo["ordenes"]] == ["Torta"]

    creadas = await _generar(client)
    assert len(creadas) == 1
    assert creadas[0]["responsable"] == "Pasteleria"
    # La orden previa quedó intacta
    todas = (await client.get("/costos/ordenes-produccion")).json()
    assert len(todas) == 2


async def test_cancelar_devuelve_los_productos_a_pendientes(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "P3", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    assert (await _preview(client))["ordenes"] == []   # cubierto

    await client.post(f"/costos/ordenes-produccion/{orden['id']}/cancelar")

    cuerpo = await _preview(client)
    assert [o["producto_base_nombre"] for o in cuerpo["ordenes"]] == ["Pan"]


async def test_en_produccion_y_finalizada_siguen_cubriendo(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "P4", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    await client.post(f"/costos/ordenes-produccion/{orden['id']}/iniciar")
    assert (await _preview(client))["ordenes"] == []

    ubicacion = (await client.post("/costos/ubicaciones", json={"nombre": "Depósito"})).json()
    await client.post(
        f"/costos/ordenes-produccion/{orden['id']}/finalizar",
        json={"lineas": [{"producto_id": pan.id, "cantidad_fabricada": 100, "ubicacion_id": ubicacion["id"]}]},
    )
    assert (await _preview(client))["ordenes"] == []


async def test_nada_pendiente_no_crea_nada(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "P5", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")
    await _generar(client)

    assert await _generar(client) == []
    assert await _count(session, OrdenProduccion) == 1


# ── Borrado ──────────────────────────────────────────────────────────────────

async def test_borrar_orden_asignada_elimina_lineas_y_reservas(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "B1", "Pan")
    await _receta(session, pan, harina, cantidad=50)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    assert await _count(session, OrdenProduccionProductoLinea) == 1
    assert await _count(session, OrdenProduccionInsumoLinea) == 1
    reservas = (await session.execute(
        select(func.count()).select_from(StockMovimiento).where(StockMovimiento.tipo == "RESERVA")
    )).scalar_one()
    assert reservas == 1

    antes = (await client.get(f"/costos/insumos/{harina.id}")).json()
    assert antes["comprometido"] == 50

    respuesta = await client.delete(f"/costos/ordenes-produccion/{orden['id']}")
    assert respuesta.status_code == 204

    assert await _count(session, OrdenProduccion) == 0
    assert await _count(session, OrdenProduccionProductoLinea) == 0
    assert await _count(session, OrdenProduccionInsumoLinea) == 0
    assert await _count(session, StockMovimiento) == 0

    despues = (await client.get(f"/costos/insumos/{harina.id}")).json()
    assert despues["comprometido"] == 0
    assert despues["cantidad"] == antes["cantidad"]  # el stock físico no se toca


async def test_borrar_orden_cancelada(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "B2", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    await client.post(f"/costos/ordenes-produccion/{orden['id']}/cancelar")

    assert (await client.delete(f"/costos/ordenes-produccion/{orden['id']}")).status_code == 204
    assert await _count(session, OrdenProduccion) == 0
    assert await _count(session, StockMovimiento) == 0


async def test_no_se_puede_borrar_en_produccion(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "B3", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    await client.post(f"/costos/ordenes-produccion/{orden['id']}/iniciar")

    respuesta = await client.delete(f"/costos/ordenes-produccion/{orden['id']}")
    assert respuesta.status_code == 422
    assert "EN_PRODUCCION" in respuesta.json()["detail"]
    assert await _count(session, OrdenProduccion) == 1


async def test_no_se_puede_borrar_finalizada(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "B4", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    await client.post(f"/costos/ordenes-produccion/{orden['id']}/iniciar")
    ubicacion = (await client.post("/costos/ubicaciones", json={"nombre": "Depósito"})).json()
    await client.post(
        f"/costos/ordenes-produccion/{orden['id']}/finalizar",
        json={"lineas": [{"producto_id": pan.id, "cantidad_fabricada": 100, "ubicacion_id": ubicacion["id"]}]},
    )

    respuesta = await client.delete(f"/costos/ordenes-produccion/{orden['id']}")
    assert respuesta.status_code == 422
    assert await _count(session, OrdenProduccion) == 1


async def test_borrar_devuelve_los_productos_a_pendientes(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "B5", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    assert (await _preview(client))["ordenes"] == []

    await client.delete(f"/costos/ordenes-produccion/{orden['id']}")

    cuerpo = await _preview(client)
    assert cuerpo["ordenes_existentes"] == 0
    assert [o["producto_base_nombre"] for o in cuerpo["ordenes"]] == ["Pan"]


async def test_borrar_una_orden_no_toca_las_reservas_de_otra(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "B6", "Pan")
    torta = await _producto(session, "B7", "Torta")
    await _receta(session, pan, harina, cantidad=50)
    await _receta(session, torta, harina, cantidad=20)
    await _programar(session, pan, 100, "Panaderia")
    await _programar(session, torta, 100, "Pasteleria")

    ordenes = await _generar(client)
    assert len(ordenes) == 2
    a_borrar = next(o for o in ordenes if o["responsable"] == "Panaderia")

    await client.delete(f"/costos/ordenes-produccion/{a_borrar['id']}")

    restantes = (await session.execute(select(StockMovimiento))).scalars().all()
    assert len(restantes) == 1
    assert restantes[0].referencia == next(o for o in ordenes if o["responsable"] == "Pasteleria")["codigo"]


# ── Cambiar el responsable ───────────────────────────────────────────────────

async def test_cambiar_responsable_de_una_orden_asignada(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "R1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    assert orden["responsable"] == "Panaderia"

    respuesta = await client.patch(
        f"/costos/ordenes-produccion/{orden['id']}", json={"responsable": "Pasteleria"}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["responsable"] == "Pasteleria"

    de_nuevo = await client.get(f"/costos/ordenes-produccion/{orden['id']}")
    assert de_nuevo.json()["responsable"] == "Pasteleria"


async def test_cambiar_responsable_en_produccion(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "R2", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    await client.post(f"/costos/ordenes-produccion/{orden['id']}/iniciar")

    respuesta = await client.patch(
        f"/costos/ordenes-produccion/{orden['id']}", json={"responsable": "Galletas"}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["responsable"] == "Galletas"


async def test_no_se_puede_cambiar_el_responsable_de_una_cancelada(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "R3", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    await client.post(f"/costos/ordenes-produccion/{orden['id']}/cancelar")

    respuesta = await client.patch(
        f"/costos/ordenes-produccion/{orden['id']}", json={"responsable": "Pastas"}
    )
    assert respuesta.status_code == 422
    assert (await client.get(f"/costos/ordenes-produccion/{orden['id']}")).json()["responsable"] == "Panaderia"


async def test_no_se_puede_cambiar_el_responsable_de_una_finalizada(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "R4", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    await client.post(f"/costos/ordenes-produccion/{orden['id']}/iniciar")
    ubicacion = (await client.post("/costos/ubicaciones", json={"nombre": "Depósito"})).json()
    await client.post(
        f"/costos/ordenes-produccion/{orden['id']}/finalizar",
        json={"lineas": [{"producto_id": pan.id, "cantidad_fabricada": 100, "ubicacion_id": ubicacion["id"]}]},
    )

    respuesta = await client.patch(
        f"/costos/ordenes-produccion/{orden['id']}", json={"responsable": "Pastas"}
    )
    assert respuesta.status_code == 422


async def test_responsable_vacio_es_rechazado(client, session):
    harina = await _insumo(session)
    pan = await _producto(session, "R5", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, 100, "Panaderia")

    orden = (await _generar(client))[0]
    respuesta = await client.patch(f"/costos/ordenes-produccion/{orden['id']}", json={"responsable": ""})
    assert respuesta.status_code in (400, 422)
