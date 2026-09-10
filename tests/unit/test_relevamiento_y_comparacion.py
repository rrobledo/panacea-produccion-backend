"""F3 de masa-procesos-y-maquinaria: relevamiento del gramaje y comparación.

Ver openspec/changes/masa-procesos-y-maquinaria/tasks.md 4.5 y 4.7 en el repo
`panacea-produccion`. El grafo todavía no manda: esto sólo mide cuánto falta
del relevamiento y muestra qué cambiaría si el motor nuevo se activara.
"""

from datetime import date

from sqlalchemy import select

from app.models.insumos import Insumos
from app.models.procesos import Proceso, ProcesoLinea
from app.models.productos import Costos, Productos
from app.models.programacion import Programacion
from app.services import explosion_service

FECHA = date(2026, 8, 25)


async def _make_producto(session, **overrides):
    defaults = dict(
        codigo="R1", categoria="PANADERIA", nombre="Producto", utilidad=30, precio_actual=1000,
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


async def _make_proceso(session, codigo, tipo, lote, lineas, unidad="KG"):
    proceso = Proceso(
        codigo=codigo, version=1, nombre=f"Proceso {codigo}", tipo=tipo, responsable="Panaderia",
        lote_referencia=lote, lote_unidad=unidad, minutos_setup=0, vigente_desde=FECHA,
    )
    proceso.lineas = [ProcesoLinea(**linea) for linea in lineas]
    session.add(proceso)
    await session.commit()
    await session.refresh(proceso)
    return proceso


async def _make_programacion(session, producto, plan):
    session.add(Programacion(
        fecha=FECHA, producto_id=producto.id, producto_nombre=producto.nombre,
        responsable="Panaderia", plan=plan, prod=None,
    ))
    await session.commit()


# ── 4.5 · avance del relevamiento ───────────────────────────────────────────

async def test_pendientes_de_relevamiento_cuenta_las_salidas_sin_gramaje(client, session):
    masa = await _make_producto(session, codigo="RM", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    uno = await _make_producto(session, codigo="RU1", nombre="Largo")
    dos = await _make_producto(session, codigo="RU2", nombre="Baguetín")
    await _make_proceso(session, "DIV-R", "DIVISION", 162, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=162, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=uno.id, cantidad=0, gramaje_g=360, orden=1),
        dict(rol="SALIDA", producto_id=dos.id, cantidad=0, gramaje_g=None, orden=2),
    ])

    response = await client.get("/costos/procesos/pendientes-relevamiento")

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["lineas_totales"] == 2
    assert cuerpo["lineas_completas"] == 1
    assert cuerpo["lineas_pendientes"] == 1
    assert cuerpo["porcentaje"] == 50.0
    assert cuerpo["pendientes"][0]["producto_nombre"] == "Baguetín"


async def test_un_producto_vendido_por_kilo_no_necesita_gramaje(client, session):
    masa = await _make_producto(session, codigo="RK0", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    frances = await _make_producto(session, codigo="RK1", nombre="Francés", unidad_base="KG")
    await _make_proceso(session, "DIV-RK", "DIVISION", 162, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=162, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=frances.id, cantidad=0, gramaje_g=None, orden=1),
    ])

    response = await client.get("/costos/procesos/pendientes-relevamiento")

    # Sale del cálculo por rendimiento del horno, no por gramaje: no cuenta como
    # pendiente del relevamiento.
    assert response.json()["lineas_totales"] == 0
    assert response.json()["porcentaje"] == 100.0


# ── Explosión por el grafo ──────────────────────────────────────────────────

async def test_la_explosion_suma_kilos_de_masa_no_unidades(session):
    harina = await _make_insumo(session, nombre="Harina")
    masa = await _make_producto(session, codigo="RE0", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    largo = await _make_producto(session, codigo="RE1", nombre="Largo")
    hamburguesa = await _make_producto(session, codigo="RE2", nombre="Hamburguesa")

    await _make_proceso(session, "ELAB-RE", "ELABORACION", 162, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=162, unidad="KG", orden=1),
    ])
    await _make_proceso(session, "DIV-RE", "DIVISION", 162, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=162, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=largo.id, cantidad=0, gramaje_g=360, orden=1),
        dict(rol="SALIDA", producto_id=hamburguesa.id, cantidad=0, gramaje_g=110, orden=2),
    ])

    resultado = await explosion_service.explotar_demanda(
        session, {largo.id: 100, hamburguesa.id: 100}
    )

    assert resultado.completo
    # 100 × 0,360 + 100 × 0,110 = 47 kg de masa, no "200 unidades".
    assert round(resultado.articulos[masa.id], 3) == 47.0
    # 47 / 162 de un lote que lleva 100 kg de harina.
    assert round(resultado.insumos[harina.id], 3) == round(100 * 47 / 162, 3)


async def test_la_explosion_marca_lo_que_no_puede_calcular(session):
    masa = await _make_producto(session, codigo="RP0", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    pan = await _make_producto(session, codigo="RP1", nombre="Sin gramaje")
    await _make_proceso(session, "DIV-RP", "DIVISION", 162, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=162, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=pan.id, cantidad=0, gramaje_g=None, orden=1),
    ])

    resultado = await explosion_service.explotar_demanda(session, {pan.id: 100})

    assert not resultado.completo
    assert "gramaje" in resultado.pendientes[0]


async def test_la_merma_de_division_agranda_el_requerimiento(session):
    harina = await _make_insumo(session)
    masa = await _make_producto(session, codigo="RMM", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    pan = await _make_producto(session, codigo="RMP", nombre="Pan")
    await _make_proceso(session, "ELAB-RM", "ELABORACION", 100, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=100, unidad="KG", orden=1),
    ])
    await _make_proceso(session, "DIV-RM", "DIVISION", 100, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=pan.id, cantidad=0, gramaje_g=1000, merma_pct=2, orden=1),
    ])

    resultado = await explosion_service.explotar_demanda(session, {pan.id: 100})

    # 100 bollos de 1 kg con 2 % de merma piden 102,04 kg, no 100.
    assert round(resultado.articulos[masa.id], 2) == 102.04


async def test_un_producto_por_kilo_vuelve_al_peso_crudo(session):
    harina = await _make_insumo(session)
    masa = await _make_producto(session, codigo="RKM", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    frances = await _make_producto(session, codigo="RKF", nombre="Francés", unidad_base="KG")
    await _make_proceso(session, "ELAB-RK", "ELABORACION", 100, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=100, unidad="KG", orden=1),
    ])
    await _make_proceso(session, "DIV-RK2", "DIVISION", 100, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=frances.id, cantidad=0, rendimiento_pct=83, orden=1),
    ])

    resultado = await explosion_service.explotar_demanda(session, {frances.id: 83})

    # 83 kg vendibles al 83 % de rendimiento salen de 100 kg de masa cruda.
    assert round(resultado.articulos[masa.id], 2) == 100.0


# ── 4.7 · el comparador ─────────────────────────────────────────────────────

async def test_comparar_muestra_los_dos_motores_lado_a_lado(client, session):
    harina = await _make_insumo(session, nombre="Harina")
    masa = await _make_producto(session, codigo="RC0", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False,
                                lote_produccion=162)
    largo = await _make_producto(session, codigo="RC1", nombre="Largo", producto_base_id=masa.id)
    hamburguesa = await _make_producto(session, codigo="RC2", nombre="Hamburguesa", producto_base_id=masa.id)
    session.add(Costos(producto_id=masa.id, insumo_id=harina.id, cantidad=100))
    await session.commit()
    await _make_programacion(session, largo, 100)
    await _make_programacion(session, hamburguesa, 100)

    await _make_proceso(session, "ELAB-RC", "ELABORACION", 162, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=162, unidad="KG", orden=1),
    ])
    await _make_proceso(session, "DIV-RC", "DIVISION", 162, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=162, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=largo.id, cantidad=0, gramaje_g=360, orden=1),
        dict(rol="SALIDA", producto_id=hamburguesa.id, cantidad=0, gramaje_g=110, orden=2),
    ])

    response = await client.post("/costos/ordenes-produccion/comparar", json={"fecha": FECHA.isoformat()})

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["comparable"] is True
    fila = next(f for f in cuerpo["filas"] if f["insumo_id"] == harina.id)
    # Motor viejo: (100 + 100) / 162 × 100 = 123 (redondeado). Motor nuevo:
    # 47 kg de masa sobre un lote de 162 → 29,01 kg de harina. El viejo sumaba
    # bollos de 360 g con bollos de 110 g como si pesaran lo mismo.
    assert fila["motor_viejo"] == 123
    assert round(fila["motor_nuevo"], 2) == 29.01
    assert fila["cambia"] is True
    assert cuerpo["insumos_que_cambian"] == 1


async def test_comparar_avisa_cuando_falta_relevamiento(client, session):
    harina = await _make_insumo(session)
    masa = await _make_producto(session, codigo="RN0", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    pan = await _make_producto(session, codigo="RN1", nombre="Pan", producto_base_id=masa.id)
    session.add(Costos(producto_id=masa.id, insumo_id=harina.id, cantidad=100))
    await session.commit()
    await _make_programacion(session, pan, 100)
    await _make_proceso(session, "DIV-RN", "DIVISION", 162, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=162, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=pan.id, cantidad=0, gramaje_g=None, orden=1),
    ])

    response = await client.post("/costos/ordenes-produccion/comparar", json={"fecha": FECHA.isoformat()})

    cuerpo = response.json()
    assert cuerpo["comparable"] is False
    assert any("gramaje" in p for p in cuerpo["pendientes"])


async def test_comparar_no_persiste_nada(client, session):
    from app.models.ordenes_produccion import OrdenProduccion

    harina = await _make_insumo(session)
    pan = await _make_producto(session, codigo="RX1", nombre="Pan")
    session.add(Costos(producto_id=pan.id, insumo_id=harina.id, cantidad=50))
    await session.commit()
    await _make_programacion(session, pan, 100)

    await client.post("/costos/ordenes-produccion/comparar", json={"fecha": FECHA.isoformat()})

    assert (await session.execute(select(OrdenProduccion))).scalars().all() == []
