"""F6 de masa-procesos-y-maquinaria: costeo por capas y costos conjuntos.

Ver openspec/changes/masa-procesos-y-maquinaria/{specs/reportes-costos/spec.md,
design.md D7 y D14} en el repo `panacea-produccion`.
"""

from datetime import date, datetime, timezone

from sqlalchemy import select

from app.models.centro_trabajo import CentroTrabajo
from app.models.insumos import Insumos
from app.models.maquinaria import Maquina, ProcesoOperacion
from app.models.ordenes_produccion import OrdenProduccion, ProductoFabricado
from app.models.procesos import Proceso, ProcesoLinea
from app.models.productos import Productos
from app.models.ubicacion import Ubicacion
from app.services import costeo_grafo_service

FECHA = date(2026, 8, 25)


async def _make_producto(session, **overrides):
    defaults = dict(
        codigo="C1", categoria="PANADERIA", nombre="Producto", utilidad=30, precio_actual=1000,
        unidad_medida="UN", lote_produccion=100, tiempo_produccion=0, responsable="Panaderia",
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
    defaults = dict(nombre="Harina", unidad_medida="KG", cantidad=100000, precio=780)
    defaults.update(overrides)
    insumo = Insumos(**defaults)
    session.add(insumo)
    await session.commit()
    await session.refresh(insumo)
    return insumo


async def _make_centro(session, nombre="Panaderia", tarifa=4500):
    centro = CentroTrabajo(nombre=nombre, tarifa_hora=tarifa, horas_turno=6, habilitado=True)
    session.add(centro)
    await session.commit()
    return centro


async def _make_proceso(session, codigo, tipo, lote, lineas, responsable="Panaderia"):
    proceso = Proceso(
        codigo=codigo, version=1, nombre=f"Proceso {codigo}", tipo=tipo, responsable=responsable,
        lote_referencia=lote, lote_unidad="KG", minutos_setup=0, vigente_desde=FECHA,
    )
    proceso.lineas = [ProcesoLinea(**linea) for linea in lineas]
    session.add(proceso)
    await session.commit()
    await session.refresh(proceso)
    return proceso


# ── 7.3 · costo del semielaborado por unidad ────────────────────────────────

async def test_costo_de_la_masa_por_kilo(session):
    await _make_centro(session)
    harina = await _make_insumo(session, nombre="Harina", precio=780)
    sal = await _make_insumo(session, nombre="Sal", precio=520)
    masa = await _make_producto(session, codigo="CM", nombre="Masa de francés", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    await _make_proceso(session, "ELAB-C", "ELABORACION", 162, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="ENTRADA", insumo_id=sal.id, cantidad=2, unidad="KG", orden=1),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=162, unidad="KG", orden=2),
    ])

    costo = await costeo_grafo_service.costo_de_articulo(session, masa.id)

    # 100 × 780 + 2 × 520 = 79.040 sobre 162 kg.
    assert round(costo.costo_insumos, 2) == 79040.0
    assert round(costo.costo_unitario, 4) == round(79040 / 162, 4)


async def test_el_semielaborado_entra_calculado_no_aplanado(session):
    await _make_centro(session)
    harina = await _make_insumo(session, precio=780)
    masa = await _make_producto(session, codigo="CM2", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    pan = await _make_producto(session, codigo="CP2", nombre="Pan", unidad_base="KG")
    await _make_proceso(session, "ELAB-C2", "ELABORACION", 100, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=100, unidad="KG", orden=1),
    ])
    await _make_proceso(session, "DIV-C2", "DIVISION", 100, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=pan.id, cantidad=100, unidad="KG", orden=1),
    ])

    costo = await costeo_grafo_service.costo_de_articulo(session, pan.id)

    assert [d["tipo"] for d in costo.detalle] == ["SEMIELABORADO"]
    assert costo.detalle[0]["nombre"] == "Masa"
    # 100 kg de masa a 780 el kilo de harina: el costo viaja entero.
    assert round(costo.costo_insumos, 2) == 78000.0


async def test_cambiar_el_precio_del_insumo_recostea_todo_lo_que_lo_consume(session):
    await _make_centro(session)
    harina = await _make_insumo(session, precio=780)
    masa = await _make_producto(session, codigo="CM3", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    pan = await _make_producto(session, codigo="CP3", nombre="Pan", unidad_base="KG")
    await _make_proceso(session, "ELAB-C3", "ELABORACION", 100, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=100, unidad="KG", orden=1),
    ])
    await _make_proceso(session, "DIV-C3", "DIVISION", 100, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=pan.id, cantidad=100, unidad="KG", orden=1),
    ])
    antes = (await costeo_grafo_service.costo_de_articulo(session, pan.id)).costo_unitario

    harina.precio = 1560
    await session.commit()
    despues = (await costeo_grafo_service.costo_de_articulo(session, pan.id)).costo_unitario

    # Sin editar ningún producto: el costo sube porque la masa subió.
    assert round(despues, 4) == round(antes * 2, 4)


# ── 7.4 y 7.6 · dos ramas de la misma masa cuestan distinto ────────────────

async def test_dos_ramas_con_distinto_tiempo_cuestan_distinto(session):
    await _make_centro(session, tarifa=4500)
    harina = await _make_insumo(session, precio=780)
    masa = await _make_producto(session, codigo="CM4", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    frances = await _make_producto(session, codigo="CF4", nombre="Francés", unidad_base="KG")
    pebete = await _make_producto(session, codigo="CB4", nombre="Pebete", unidad_base="UN")
    await _make_proceso(session, "ELAB-C4", "ELABORACION", 100, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=100, unidad="KG", orden=1),
    ])
    await _make_proceso(session, "DIV-CF4", "DIVISION", 100, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=100, unidad="KG", minutos_directos=90, orden=0),
        dict(rol="SALIDA", producto_id=frances.id, cantidad=100, unidad="KG", orden=1),
    ])
    await _make_proceso(session, "DIV-CB4", "DIVISION", 100, [
        dict(rol="ENTRADA", producto_id=masa.id, cantidad=100, unidad="KG", minutos_directos=150, orden=0),
        dict(rol="SALIDA", producto_id=pebete.id, cantidad=100, unidad="UN", orden=1),
    ])

    costo_frances = await costeo_grafo_service.costo_de_articulo(session, frances.id)
    costo_pebete = await costeo_grafo_service.costo_de_articulo(session, pebete.id)

    # Misma masa, mismo costo de insumos; distinto tiempo de formado.
    assert costo_frances.costo_insumos == costo_pebete.costo_insumos
    assert round(costo_frances.costo_mano_obra, 2) == round(90 / 60 * 4500, 2)
    assert round(costo_pebete.costo_mano_obra, 2) == round(150 / 60 * 4500, 2)
    assert costo_pebete.costo_total > costo_frances.costo_total


async def test_la_fermentacion_suma_maquina_y_no_mano_de_obra(session):
    await _make_centro(session, tarifa=4500)
    harina = await _make_insumo(session, precio=780)
    masa = await _make_producto(session, codigo="CM5", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    proceso = await _make_proceso(session, "ELAB-C5", "ELABORACION", 100, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=100, unidad="KG", orden=1),
    ])
    session.add(Maquina(
        codigo="CAM", nombre="Cámara", tipo="CAMARA", capacidad=12, capacidad_unidad="CARROS",
        minutos_setup=0, minutos_limpieza=0, tarifa_hora=600, area="Panaderia", estado="ACTIVA",
    ))
    await session.commit()
    session.add(ProcesoOperacion(
        proceso_id=proceso.id, orden=0, nombre="Fermentación", maquina_tipo="CAMARA",
        minutos_por_bacha=90, minutos_por_unidad=0, requiere_operario=False,
    ))
    await session.commit()

    costo = await costeo_grafo_service.costo_de_articulo(session, masa.id)

    # 9 bachas de 12 carros para 100 unidades: la máquina cuesta, el operario no.
    assert costo.costo_maquina > 0
    assert costo.costo_mano_obra == 0


# ── 7.7 y 7.8 · reparto del costo conjunto por peso ────────────────────────

async def test_el_reparto_por_peso_absorbe_el_residuo_sin_valor(session):
    await _make_centro(session, tarifa=0)
    plancha_insumo = await _make_insumo(session, nombre="Mezcla", precio=3000)
    plancha = await _make_producto(session, codigo="CB", nombre="Plancha", is_producto=False,
                                   naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    cuadrado = await _make_producto(session, codigo="CQ", nombre="Cuadrado", unidad_base="UN")
    disco = await _make_producto(session, codigo="CD", nombre="Disco", unidad_base="UN")
    recorte = await _make_producto(session, codigo="CR", nombre="Recorte", unidad_base="KG",
                                   naturaleza="RESIDUO", vendible=False)

    await _make_proceso(session, "ELAB-CB", "ELABORACION", 6, [
        dict(rol="ENTRADA", insumo_id=plancha_insumo.id, cantidad=6, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=plancha.id, cantidad=6, unidad="KG", orden=1),
    ])
    await _make_proceso(session, "FRAC-CB", "FRACCIONAMIENTO", 6, [
        dict(rol="ENTRADA", producto_id=plancha.id, cantidad=6, unidad="KG", orden=0),
        dict(rol="COPRODUCTO", producto_id=cuadrado.id, cantidad=48, gramaje_g=90, orden=1),
        dict(rol="COPRODUCTO", producto_id=disco.id, cantidad=12, gramaje_g=100, orden=2),
        dict(rol="RESIDUO", producto_id=recorte.id, cantidad=0.48, unidad="KG", orden=3),
    ])

    costo_cuadrado = await costeo_grafo_service.costo_de_articulo(session, cuadrado.id)
    costo_disco = await costeo_grafo_service.costo_de_articulo(session, disco.id)

    # 4,32 kg de cuadrados y 1,20 de discos sobre 5,52 kg de salida útil: el
    # recorte de 0,48 kg no recibe costo, se absorbe entre los dos.
    total = costo_cuadrado.costo_total + costo_disco.costo_total
    assert round(total, 2) == round(6 * 3000, 2)
    assert round(costo_cuadrado.costo_total / total, 4) == round(4.32 / 5.52, 4)


# ── 7.11 · desvío de merma ──────────────────────────────────────────────────

async def test_el_desvio_compara_la_merma_real_contra_la_declarada(client, session):
    masa = await _make_producto(session, codigo="CDM", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    await _make_proceso(session, "ELAB-CDM", "ELABORACION", 100, [
        dict(rol="SALIDA", producto_id=masa.id, cantidad=100, unidad="KG", merma_pct=2, orden=0),
    ])
    ubicacion = Ubicacion(nombre="Cámara")
    orden = OrdenProduccion(
        codigo="260101-01", fecha_fabricacion=FECHA, responsable="Panaderia", estado="FINALIZADA",
        fecha_creacion=datetime.now(timezone.utc),
    )
    session.add_all([ubicacion, orden])
    await session.commit()
    session.add(ProductoFabricado(
        orden_id=orden.id, producto_id=masa.id, cantidad_fabricada=90,
        ubicacion_id=ubicacion.id, cantidad_desperdicio=10, fecha=datetime.now(timezone.utc),
    ))
    await session.commit()

    response = await client.get("/costos/desvio-merma")

    assert response.status_code == 200
    fila = response.json()[0]
    # 10 de 100 es 10 % real contra 2 % declarado: 8 puntos de desvío.
    assert fila["merma_real_pct"] == 10.0
    assert fila["merma_declarada_pct"] == 2.0
    assert fila["desvio_pct"] == 8.0


# ── 7.1 · centro de trabajo ─────────────────────────────────────────────────

async def test_alta_y_edicion_de_centro_de_trabajo(client, session):
    creado = await client.post(
        "/costos/centros-trabajo",
        json={"nombre": "Panaderia", "tarifa_hora": 4500, "horas_turno": 6, "habilitado": True},
    )
    assert creado.status_code == 201

    editado = await client.put(
        f"/costos/centros-trabajo/{creado.json()['id']}",
        json={"nombre": "Panaderia", "tarifa_hora": 5000, "horas_turno": 8, "habilitado": True},
    )
    assert editado.status_code == 200
    assert editado.json()["tarifa_hora"] == 5000


async def test_centro_repetido_es_rechazado(client, session):
    payload = {"nombre": "Pastas", "tarifa_hora": 1, "horas_turno": 6, "habilitado": True}
    await client.post("/costos/centros-trabajo", json=payload)
    response = await client.post("/costos/centros-trabajo", json=payload)
    assert response.status_code == 422


# ── 7.9 · el endpoint de costeo ─────────────────────────────────────────────

async def test_el_endpoint_devuelve_las_tres_capas(client, session):
    await _make_centro(session)
    harina = await _make_insumo(session, precio=780)
    masa = await _make_producto(session, codigo="CE", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    await _make_proceso(session, "ELAB-CE", "ELABORACION", 100, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=100, unidad="KG", orden=1),
    ])

    response = await client.get(f"/costos/costeo-grafo/{masa.id}")

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["costo_insumos"] == 78000.0
    assert "costo_mano_obra" in cuerpo and "costo_maquina" in cuerpo
    assert cuerpo["costo_unitario"] == 780.0


async def test_un_articulo_sin_proceso_lo_dice(client, session):
    huerfano = await _make_producto(session, codigo="CH", nombre="Huérfano")

    response = await client.get(f"/costos/costeo-grafo/{huerfano.id}")

    assert response.status_code == 200
    assert any("no es salida" in p for p in response.json()["pendientes"])


# ── 7.9 y 7.10 · el reporte de materia prima sobre el costo por capas ──────

async def test_costos_materia_prima_usa_las_capas_con_el_flag(client, session, monkeypatch):
    from app.config import get_settings as _settings

    await _make_centro(session)
    harina = await _make_insumo(session, precio=780)
    masa = await _make_producto(session, codigo="CF", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False,
                                lote_produccion=100, tiempo_produccion=40)
    await _make_proceso(session, "ELAB-CF", "ELABORACION", 100, [
        dict(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        dict(rol="SALIDA", producto_id=masa.id, cantidad=100, unidad="KG", orden=1),
    ])

    sin_flag = await client.get(f"/costos/costos_materia_prima/{masa.id}")
    assert sin_flag.json()["costeo_por_capas"] is False

    monkeypatch.setenv("MOTOR_GRAFO", "true")
    _settings.cache_clear()
    try:
        con_flag = await client.get(f"/costos/costos_materia_prima/{masa.id}")
    finally:
        _settings.cache_clear()

    cuerpo = con_flag.json()
    assert cuerpo["costeo_por_capas"] is True
    assert cuerpo["costo_unitario_mp"] == 780.0
    # Una sola figura por concepto, sin el par costo_*/costo_*_new.
    assert "costo_unitario_maquina" in cuerpo
