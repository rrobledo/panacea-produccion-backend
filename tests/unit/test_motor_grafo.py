"""F4 de masa-procesos-y-maquinaria: el motor del grafo detrás del flag.

Ver openspec/changes/masa-procesos-y-maquinaria/tasks.md 5.1-5.13 en el repo
`panacea-produccion`. Con `MOTOR_GRAFO=false` (el default) nada cambia; con
`true`, la explosión pasa a sumar kilos de masa en vez de unidades sueltas.
"""

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.config import get_settings
from app.models.insumos import Insumos
from app.models.ordenes_produccion import OrdenProduccion, OrdenProduccionProductoLinea
from app.models.procesos import Proceso, ProcesoLinea
from app.models.productos import Costos, Productos
from app.models.programacion import Programacion
from app.models.stock_movimiento import StockMovimiento
from app.services import explosion_service, stock_service

FECHA = date(2026, 8, 25)


@pytest_asyncio.fixture
async def motor_grafo(monkeypatch):
    """Prende el flag del motor nuevo mientras dura el test."""
    monkeypatch.setenv("MOTOR_GRAFO", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _make_producto(session, **overrides):
    defaults = dict(
        codigo="M1", categoria="PANADERIA", nombre="Producto", utilidad=30, precio_actual=1000,
        unidad_medida="UN", lote_produccion=100, tiempo_produccion=2, responsable="Panaderia",
        is_producto=True, habilitado=True, prioridad=10,
        naturaleza="TERMINADO", unidad_base="UN", vendible=True,
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


async def _make_proceso(session, codigo, tipo, lote, lineas, minimo=None, multiplo=None, unidad="KG"):
    proceso = Proceso(
        codigo=codigo, version=1, nombre=f"Proceso {codigo}", tipo=tipo, responsable="Panaderia",
        lote_referencia=lote, lote_unidad=unidad, lote_minimo=minimo, lote_multiplo=multiplo,
        minutos_setup=0, vigente_desde=FECHA,
    )
    proceso.lineas = [ProcesoLinea(**linea) for linea in lineas]
    session.add(proceso)
    await session.commit()
    await session.refresh(proceso)
    return proceso


async def _programar(session, producto, plan):
    session.add(Programacion(
        fecha=FECHA, producto_id=producto.id, producto_nombre=producto.nombre,
        responsable="Panaderia", plan=plan, prod=None,
    ))
    await session.commit()


async def _escenario_frances(session, minimo=162, multiplo=162):
    """La masa de francés partida en dos gramajes: el caso 1 del relevamiento."""
    harina = await _make_insumo(session, nombre="Harina")
    masa = await _make_producto(session, codigo="MF0", nombre="Masa de francés", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False,
                                lote_produccion=162)
    largo = await _make_producto(session, codigo="MF1", nombre="Largo", producto_base_id=masa.id)
    hamburguesa = await _make_producto(session, codigo="MF2", nombre="Hamburguesa", producto_base_id=masa.id)
    session.add(Costos(producto_id=masa.id, insumo_id=harina.id, cantidad=100))
    await session.commit()

    await _make_proceso(session, "ELAB-MF", "ELABORACION", 162, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=162, unidad="KG", orden=1),
    ], minimo=minimo, multiplo=multiplo)
    await _make_proceso(session, "DIV-MF", "DIVISION", 162, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=162, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=largo.id, cantidad=0, gramaje_g=360, orden=1),
        dict(rol="SALIDA", producto_id=hamburguesa.id, cantidad=0, gramaje_g=110, orden=2),
    ])
    return harina, masa, largo, hamburguesa


# ── 5.9 · el flag ───────────────────────────────────────────────────────────

async def test_sin_el_flag_manda_el_motor_viejo(client, session):
    harina, masa, largo, hamburguesa = await _escenario_frances(session)
    await _programar(session, largo, 100)
    await _programar(session, hamburguesa, 100)

    response = await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})

    orden = response.json()["ordenes"][0]
    # (100 + 100) / 162 × 100 = 123, el cálculo que suma bollos de 360 g con
    # bollos de 110 g como si pesaran lo mismo.
    assert orden["insumos"][0]["cantidad"] == 123
    assert orden["proceso_id"] is None


# ── 5.1 y 5.2 · la explosión por el grafo ───────────────────────────────────

async def test_con_el_flag_suma_kilos_de_masa(client, session, motor_grafo):
    harina, masa, largo, hamburguesa = await _escenario_frances(session)
    await _programar(session, largo, 100)
    await _programar(session, hamburguesa, 100)

    response = await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})

    orden = response.json()["ordenes"][0]
    # 100 × 0,360 + 100 × 0,110 = 47 kg de masa. Como el lote mínimo son 162 kg,
    # se amasa un lote entero y sobran 115.
    assert orden["masa_requerida"] == 47.0
    assert orden["lote_producido"] == 162.0
    assert orden["sobrante"] == 115.0
    assert orden["insumos"][0]["cantidad"] == 100.0
    assert orden["proceso_id"] is not None


async def test_cada_rama_lleva_su_masa_su_gramaje_y_sus_bollos(client, session, motor_grafo):
    harina, masa, largo, hamburguesa = await _escenario_frances(session)
    await _programar(session, largo, 100)
    await _programar(session, hamburguesa, 100)

    response = await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})

    ramas = {p["producto_nombre"]: p for p in response.json()["ordenes"][0]["productos"]}
    assert ramas["Largo"]["masa_kg"] == 36.0
    assert ramas["Largo"]["gramaje_g"] == 360
    assert ramas["Largo"]["bollos"] == 100
    assert ramas["Hamburguesa"]["masa_kg"] == 11.0


async def test_un_producto_por_kilo_vuelve_al_peso_crudo(client, session, motor_grafo):
    harina = await _make_insumo(session)
    masa = await _make_producto(session, codigo="MK0", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    frances = await _make_producto(session, codigo="MK1", nombre="Francés", unidad_base="KG",
                                   producto_base_id=masa.id)
    await _make_proceso(session, "ELAB-MK", "ELABORACION", 100, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=100, unidad="KG", orden=1),
    ], minimo=100, multiplo=100)
    await _make_proceso(session, "DIV-MK", "DIVISION", 100, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=frances.id, cantidad=0, gramaje_g=360, rendimiento_pct=83, orden=1),
    ])
    await _programar(session, frances, 83)

    response = await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})

    orden = response.json()["ordenes"][0]
    assert orden["masa_requerida"] == 100.0
    # 83 kg vendibles a 360 g crudos con 83 % de rendimiento son 278 bollos.
    assert orden["productos"][0]["bollos"] == 278


# ── 5.3 · redondeo a lote ───────────────────────────────────────────────────

def test_el_redondeo_a_lote_siempre_va_para_arriba():
    assert explosion_service.redondear_a_lote(47, 162, 162) == 162
    assert explosion_service.redondear_a_lote(200, 162, 162) == 324
    assert explosion_service.redondear_a_lote(324, 162, 162) == 324
    assert explosion_service.redondear_a_lote(0, 162, 162) == 0
    # Sin múltiplo declarado, sólo se respeta el mínimo.
    assert explosion_service.redondear_a_lote(50, 162, None) == 162
    assert explosion_service.redondear_a_lote(200, 162, None) == 200


# ── 5.4 · el stock de masa se consume antes de amasar ───────────────────────

async def test_el_stock_de_masa_se_descuenta_antes_de_redondear(client, session, motor_grafo):
    harina, masa, largo, hamburguesa = await _escenario_frances(session, minimo=100, multiplo=100)
    await _programar(session, largo, 100)
    orden_previa = OrdenProduccion(
        codigo="260101-99", fecha_fabricacion=FECHA, responsable="Panaderia", estado="FINALIZADA",
        fecha_creacion=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    session.add(orden_previa)
    await session.commit()
    session.add(stock_service.crear_produccion(masa.id, 20, orden_previa.codigo, orden_previa.id))
    await session.commit()

    response = await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})

    orden = response.json()["ordenes"][0]
    # Pide 36 kg, hay 20 en stock: sólo hace falta amasar 16, que redondea a 100.
    assert orden["masa_requerida"] == 36.0
    assert orden["masa_desde_stock"] == 20.0
    assert orden["lote_producido"] == 100.0


async def test_generar_consume_el_stock_que_uso(client, session, motor_grafo):
    harina, masa, largo, hamburguesa = await _escenario_frances(session, minimo=100, multiplo=100)
    await _programar(session, largo, 100)
    orden_previa = OrdenProduccion(
        codigo="260101-99", fecha_fabricacion=FECHA, responsable="Panaderia", estado="FINALIZADA",
        fecha_creacion=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    session.add(orden_previa)
    await session.commit()
    session.add(stock_service.crear_produccion(masa.id, 20, orden_previa.codigo, orden_previa.id))
    await session.commit()

    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})

    # El saldo se consume: si quedara disponible, la orden siguiente lo contaría
    # una segunda vez.
    assert await stock_service.disponible_de_articulo(session, masa.id) == 0
    consumos = (
        await session.execute(select(StockMovimiento).where(StockMovimiento.tipo == "CONSUMO_INTERNO"))
    ).scalars().all()
    assert len(consumos) == 1


# ── 5.5 · redondeo de insumos sensible a la unidad ──────────────────────────

def test_el_redondeo_de_insumos_respeta_la_unidad():
    assert explosion_service.redondear_insumo(12.4, "UN") == 12
    assert explosion_service.redondear_insumo(12.5, "UN") == 13
    # El piso de 1 desaparece: 0,4 kg se reservan como 0,4, no como 1.
    assert explosion_service.redondear_insumo(0.4, "KG") == 0.4
    assert explosion_service.redondear_insumo(1348.6666, "GR") == 1348.667
    assert explosion_service.redondear_insumo(0, "KG") == 0


async def test_un_insumo_en_kilos_no_se_sobre_reserva(client, session, motor_grafo):
    harina = await _make_insumo(session, nombre="Harina", unidad_medida="KG")
    malta = await _make_insumo(session, nombre="Malta", unidad_medida="KG")
    masa = await _make_producto(session, codigo="MR0", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    pan = await _make_producto(session, codigo="MR1", nombre="Pan", producto_base_id=masa.id)
    await _make_proceso(session, "ELAB-MR", "ELABORACION", 100, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="ENTRADA", insumo_id=malta.id, cantidad=0.4, unidad="KG", orden=1),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=100, unidad="KG", orden=2),
    ], minimo=100, multiplo=100)
    await _make_proceso(session, "DIV-MR", "DIVISION", 100, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=pan.id, cantidad=0, gramaje_g=1000, orden=1),
    ])
    await _programar(session, pan, 100)

    response = await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})

    cantidades = {i["insumo_nombre"]: i["cantidad"] for i in response.json()["ordenes"][0]["insumos"]}
    assert cantidades["Malta"] == 0.4


# ── 5.7 y 5.8 · lo que la orden guarda ──────────────────────────────────────

async def test_la_orden_congela_el_proceso_y_su_version(client, session, motor_grafo):
    harina, masa, largo, hamburguesa = await _escenario_frances(session)
    await _programar(session, largo, 100)

    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})

    orden = (await session.execute(select(OrdenProduccion))).scalars().one()
    division = (
        await session.execute(select(Proceso).where(Proceso.codigo == "DIV-MF"))
    ).scalars().one()
    assert orden.proceso_id == division.id
    assert orden.proceso_version == 1
    assert orden.masa_requerida == 36.0
    assert orden.lote_producido == 162.0


async def test_la_linea_guarda_masa_gramaje_y_bollos(client, session, motor_grafo):
    harina, masa, largo, hamburguesa = await _escenario_frances(session)
    await _programar(session, largo, 100)

    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})

    linea = (await session.execute(select(OrdenProduccionProductoLinea))).scalars().one()
    assert (linea.masa_kg, linea.gramaje_g, linea.bollos) == (36.0, 360.0, 100)
    assert linea.programacion_id is not None


# ── 5.13 · lo que ya existía sigue funcionando ──────────────────────────────

async def test_el_ciclo_de_vida_de_la_orden_no_cambia(client, session, motor_grafo):
    harina, masa, largo, hamburguesa = await _escenario_frances(session)
    await _programar(session, largo, 100)
    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    orden = (await session.execute(select(OrdenProduccion))).scalars().one()

    assert (await client.post(f"/costos/ordenes-produccion/{orden.id}/iniciar")).status_code == 200
    detalle = await client.get(f"/costos/ordenes-produccion/{orden.id}")
    assert detalle.status_code == 200
    assert detalle.json()["estado"] == "EN_PRODUCCION"
    assert detalle.json()["productos"][0]["bollos"] == 100


async def test_una_orden_generada_por_el_motor_nuevo_se_puede_borrar(client, session, motor_grafo):
    harina, masa, largo, hamburguesa = await _escenario_frances(session)
    await _programar(session, largo, 100)
    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    orden = (await session.execute(select(OrdenProduccion))).scalars().one()

    assert (await client.delete(f"/costos/ordenes-produccion/{orden.id}")).status_code == 204
    assert (await session.execute(select(StockMovimiento))).scalars().all() == []


async def test_una_rama_sin_gramaje_se_reporta_como_pendiente(client, session, motor_grafo):
    harina = await _make_insumo(session)
    masa = await _make_producto(session, codigo="MP0", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    pan = await _make_producto(session, codigo="MP1", nombre="Pan", producto_base_id=masa.id)
    await _make_proceso(session, "ELAB-MP", "ELABORACION", 100, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=100, unidad="KG", orden=1),
    ])
    await _make_proceso(session, "DIV-MP", "DIVISION", 100, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=pan.id, cantidad=0, gramaje_g=None, orden=1),
    ])
    await _programar(session, pan, 100)

    response = await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})

    # Sin gramaje no hay orden que generar, y el preview dice por qué en vez de
    # devolver una cantidad inventada.
    assert response.json()["ordenes"] == []
