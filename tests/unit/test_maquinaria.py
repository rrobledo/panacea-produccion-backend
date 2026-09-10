"""F5 de masa-procesos-y-maquinaria: maquinaria y carga del día.

Ver openspec/changes/masa-procesos-y-maquinaria/{specs/maquinaria/spec.md,
tasks.md 6.1-6.17} en el repo `panacea-produccion`. El alcance es N2: detectar
que el día no entra, no planificar horarios.
"""

from datetime import date, datetime, timezone

import pytest_asyncio
from sqlalchemy import select

from app.config import get_settings
from app.models.insumos import Insumos
from app.models.maquinaria import Maquina, OrdenOperacion
from app.models.ordenes_produccion import OrdenProduccion
from app.models.procesos import Proceso, ProcesoLinea
from app.models.productos import Productos
from app.models.programacion import Programacion
from app.services import maquinaria_service

FECHA = date(2026, 8, 25)


@pytest_asyncio.fixture
async def motor_grafo(monkeypatch):
    monkeypatch.setenv("MOTOR_GRAFO", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _maquina(**overrides):
    defaults = dict(
        codigo="AM1", nombre="Amasadora 60", tipo="AMASADORA", capacidad=60, capacidad_unidad="KG",
        minutos_setup=5, minutos_limpieza=10, tarifa_hora=1200, area="Panaderia", estado="ACTIVA",
        turno_desde="04:00", turno_hasta="10:00",
    )
    defaults.update(overrides)
    return defaults


async def _crear_maquina(client, **overrides):
    response = await client.post("/costos/maquinas", json=_maquina(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


async def _make_producto(session, **overrides):
    defaults = dict(
        codigo="Q1", categoria="PANADERIA", nombre="Producto", utilidad=30, precio_actual=1000,
        unidad_medida="UN", lote_produccion=162, tiempo_produccion=2, responsable="Panaderia",
        is_producto=True, habilitado=True, prioridad=10,
        naturaleza="TERMINADO", unidad_base="UN", vendible=True,
    )
    defaults.update(overrides)
    producto = Productos(**defaults)
    session.add(producto)
    await session.commit()
    await session.refresh(producto)
    return producto


# ── 6.4 · catálogo ──────────────────────────────────────────────────────────

async def test_alta_de_maquina(client, session):
    creada = await _crear_maquina(client)
    assert creada["tipo"] == "AMASADORA"
    assert creada["capacidad_unidad"] == "KG"


async def test_capacidad_sin_unidad_valida_es_rechazada(client, session):
    response = await client.post("/costos/maquinas", json=_maquina(capacidad_unidad="PALETAS"))
    assert response.status_code == 422
    assert "Unidad de capacidad" in response.json()["detail"]


async def test_tipo_invalido_es_rechazado(client, session):
    response = await client.post("/costos/maquinas", json=_maquina(tipo="TOSTADORA"))
    assert response.status_code == 422


async def test_codigo_repetido_es_rechazado(client, session):
    await _crear_maquina(client)
    response = await client.post("/costos/maquinas", json=_maquina(nombre="Otra"))
    assert response.status_code == 422


# ── 6.5 · bachas ────────────────────────────────────────────────────────────

def test_las_bachas_se_redondean_para_arriba():
    assert maquinaria_service.calcular_bachas(162, 60) == 3
    assert maquinaria_service.calcular_bachas(120, 60) == 2
    assert maquinaria_service.calcular_bachas(61, 60) == 2
    assert maquinaria_service.calcular_bachas(0, 60) == 0


def test_el_tiempo_sale_de_las_bachas_no_de_una_amasada():
    from app.models.maquinaria import ProcesoOperacion

    maquina = Maquina(**_maquina())
    operacion = ProcesoOperacion(
        nombre="Amasado", maquina_tipo="AMASADORA", minutos_por_bacha=12, minutos_por_unidad=0,
    )
    bachas, minutos = maquinaria_service.minutos_de_operacion(operacion, maquina, 162)
    # 3 × (5 de setup + 12 de amasada) + 10 de limpieza = 61, no 40.
    assert (bachas, minutos) == (3, 61)


# ── 6.7 · resolución de máquina por tipo ────────────────────────────────────

async def test_se_elige_la_maquina_mas_chica_que_alcanza(client, session):
    await _crear_maquina(client, codigo="AM-CHICA", nombre="Amasadora 30", capacidad=30)
    await _crear_maquina(client, codigo="AM-GRANDE", nombre="Amasadora 80", capacidad=80)

    elegida = await maquinaria_service.resolver_maquina(session, "AMASADORA", 30)

    # Usar la grande para una masa chica ocupa un recurso escaso sin necesidad.
    assert elegida.nombre == "Amasadora 30"


async def test_la_capacidad_minima_descarta_las_que_no_alcanzan(client, session):
    await _crear_maquina(client, codigo="AM-CHICA", nombre="Amasadora 30", capacidad=30)
    await _crear_maquina(client, codigo="AM-GRANDE", nombre="Amasadora 80", capacidad=80)

    elegida = await maquinaria_service.resolver_maquina(session, "AMASADORA", 60)

    assert elegida.nombre == "Amasadora 80"


async def test_una_maquina_en_mantenimiento_sale_del_calculo(client, session):
    await _crear_maquina(client, estado="MANTENIMIENTO")

    assert await maquinaria_service.resolver_maquina(session, "AMASADORA", None) is None


# ── 6.8 · exclusiva vs concurrente ──────────────────────────────────────────

async def test_la_camara_se_cuenta_en_carros_y_la_amasadora_en_horas(client, session):
    await _crear_maquina(client, codigo="AM", tipo="AMASADORA", capacidad=60, capacidad_unidad="KG")
    await _crear_maquina(
        client, codigo="CAM", nombre="Cámara", tipo="CAMARA", capacidad=12, capacidad_unidad="CARROS",
    )

    carga = await maquinaria_service.carga_del_dia(session, FECHA)

    por_tipo = {f["tipo"]: f for f in carga["filas"]}
    assert por_tipo["AMASADORA"]["concurrente"] is False
    assert por_tipo["CAMARA"]["concurrente"] is True
    # 6 h de turno × 12 carros simultáneos.
    assert por_tipo["CAMARA"]["capacidad_horas"] == 72.0
    assert por_tipo["AMASADORA"]["capacidad_horas"] == 6.0


# ── 6.10 y 6.11 · carga del día y aviso ─────────────────────────────────────

async def _escenario_con_operaciones(client, session, minutos_por_bacha=12, capacidad=60):
    harina = Insumos(nombre="Harina", unidad_medida="KG", cantidad=100000, precio=1000)
    session.add(harina)
    await session.commit()
    await session.refresh(harina)

    masa = await _make_producto(session, codigo="QM", nombre="Masa", is_producto=False,
                                naturaleza="SEMIELABORADO", unidad_base="KG", vendible=False)
    pan = await _make_producto(session, codigo="QP", nombre="Pan", producto_base_id=masa.id)

    elab = Proceso(
        codigo="ELAB-Q", version=1, nombre="Masa", tipo="ELABORACION", responsable="Panaderia",
        lote_referencia=162, lote_unidad="KG", lote_minimo=162, lote_multiplo=162,
        minutos_setup=0, vigente_desde=FECHA,
    )
    elab.lineas = [
        ProcesoLinea(rol="ENTRADA", insumo_id=harina.id, cantidad=100, unidad="KG", orden=0),
        ProcesoLinea(rol="SALIDA", producto_id=masa.id, cantidad=162, unidad="KG", orden=1),
    ]
    div = Proceso(
        codigo="DIV-Q", version=1, nombre="División", tipo="DIVISION", responsable="Panaderia",
        lote_referencia=162, lote_unidad="KG", minutos_setup=0, vigente_desde=FECHA,
    )
    div.lineas = [
        ProcesoLinea(rol="ENTRADA", producto_id=masa.id, cantidad=162, unidad="KG", orden=0),
        ProcesoLinea(rol="SALIDA", producto_id=pan.id, cantidad=0, gramaje_g=360, orden=1),
    ]
    session.add_all([elab, div])
    await session.commit()
    await session.refresh(div)

    await _crear_maquina(client, codigo="AM-Q", capacidad=capacidad)
    from app.models.maquinaria import ProcesoOperacion
    session.add(ProcesoOperacion(
        proceso_id=div.id, orden=0, nombre="Amasado", maquina_tipo="AMASADORA",
        minutos_por_bacha=minutos_por_bacha, requiere_operario=True,
    ))
    session.add(Programacion(
        fecha=FECHA, producto_id=pan.id, producto_nombre=pan.nombre,
        responsable="Panaderia", plan=100, prod=None,
    ))
    await session.commit()
    return div, pan


async def test_la_orden_resuelve_sus_operaciones_al_emitirse(client, session, motor_grafo):
    await _escenario_con_operaciones(client, session)

    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})

    operaciones = (await session.execute(select(OrdenOperacion))).scalars().all()
    assert len(operaciones) == 1
    assert operaciones[0].maquina_id is not None
    # 162 kg en una amasadora de 60 son 3 bachas.
    assert operaciones[0].bachas == 3
    assert operaciones[0].minutos == 61


async def test_sin_maquina_que_sirva_la_orden_se_emite_igual(client, session, motor_grafo):
    div, pan = await _escenario_con_operaciones(client, session)
    maquina = (await session.execute(select(Maquina))).scalars().one()
    maquina.estado = "MANTENIMIENTO"
    await session.commit()

    response = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})

    assert response.status_code == 201
    operacion = (await session.execute(select(OrdenOperacion))).scalars().one()
    # Se emite igual, con la operación marcada como no resuelta: no hace falta
    # editar ninguna receta para sacar una máquina de circulación.
    assert operacion.maquina_id is None


async def test_el_tablero_de_carga_ordena_por_uso(client, session, motor_grafo):
    await _escenario_con_operaciones(client, session)
    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})

    response = await client.get(f"/costos/carga-dia?fecha={FECHA.isoformat()}")

    assert response.status_code == 200
    filas = response.json()["filas"]
    assert filas[0]["tipo"] == "AMASADORA"
    assert filas[0]["requerido_horas"] == round(61 / 60, 2)
    assert filas[0]["estado"] == "HOLGADO"


async def test_el_preview_avisa_cuando_el_dia_no_entra(client, session, motor_grafo):
    # Una operación de 200 minutos por bacha: 3 bachas se pasan del turno de 6 h.
    await _escenario_con_operaciones(client, session, minutos_por_bacha=200)

    response = await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})

    avisos = response.json()["avisos_capacidad"]
    assert len(avisos) == 1
    assert "Amasadora" in avisos[0]
    assert "de más" in avisos[0]


async def test_sin_sobrecapacidad_no_hay_aviso(client, session, motor_grafo):
    await _escenario_con_operaciones(client, session)

    response = await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})

    assert response.json()["avisos_capacidad"] == []


# ── 6.9 · ocupar la máquina sin ocupar al operario ──────────────────────────

def test_una_operacion_sin_operario_no_cuenta_como_mano_de_obra():
    from app.models.maquinaria import ProcesoOperacion

    camara = Maquina(**_maquina(
        codigo="CAM", nombre="Cámara", tipo="CAMARA", capacidad=12, capacidad_unidad="CARROS",
        minutos_setup=0, minutos_limpieza=0,
    ))
    operacion = ProcesoOperacion(
        nombre="Fermentación", maquina_tipo="CAMARA", minutos_por_bacha=90, requiere_operario=False,
    )
    bachas, minutos = maquinaria_service.minutos_de_operacion(operacion, camara, 6)
    assert minutos == 90
    # El consumo de operario lo decide el flag, no el tiempo de máquina.
    assert operacion.requiere_operario is False


# ── 6.12 · validación blanda de lote contra capacidad ───────────────────────

async def test_el_lote_que_desperdicia_bacha_avisa_sin_bloquear(client, session):
    div, pan = await _escenario_con_operaciones(client, session)

    response = await client.get(f"/costos/procesos/{div.id}")

    assert response.status_code == 200
    avisos = response.json()["advertencias"]
    # 162 kg en una amasadora de 60: la tercera bacha corre a 42 de 60.
    assert any("42" in aviso and "bachas" in aviso for aviso in avisos)


async def test_un_lote_multiplo_de_la_capacidad_no_avisa(client, session):
    div, pan = await _escenario_con_operaciones(client, session, capacidad=81)

    response = await client.get(f"/costos/procesos/{div.id}")

    assert not any("bachas" in aviso for aviso in response.json()["advertencias"])


# ── 6.14 · las operaciones viajan con el proceso ────────────────────────────

async def test_las_operaciones_se_guardan_y_se_leen_con_el_proceso(client, session):
    pan = await _make_producto(session, codigo="QOP", nombre="Pan")
    payload = {
        "codigo": "P-OPS", "nombre": "Con etapas", "tipo": "ELABORACION", "responsable": "Panaderia",
        "lote_referencia": 100, "lote_unidad": "KG", "lote_minimo": None, "lote_multiplo": None,
        "minutos_setup": 0,
        "lineas": [{"rol": "SALIDA", "producto_id": pan.id, "cantidad": 100, "unidad": "KG"}],
        "operaciones": [
            {"orden": 0, "nombre": "Amasado", "maquina_tipo": "AMASADORA", "capacidad_minima": 60,
             "minutos_por_bacha": 12, "minutos_por_unidad": 0, "requiere_operario": True,
             "puede_solapar": False},
            {"orden": 1, "nombre": "Fermentación", "maquina_tipo": "CAMARA", "capacidad_minima": None,
             "minutos_por_bacha": 90, "minutos_por_unidad": 0, "requiere_operario": False,
             "puede_solapar": True},
        ],
    }

    creado = await client.post("/costos/procesos", json=payload)

    assert creado.status_code == 201
    operaciones = creado.json()["operaciones"]
    assert [o["nombre"] for o in operaciones] == ["Amasado", "Fermentación"]
    assert operaciones[1]["requiere_operario"] is False


async def test_borrar_una_maquina_usada_por_una_orden_es_rechazado(client, session, motor_grafo):
    await _escenario_con_operaciones(client, session)
    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    maquina = (await session.execute(select(Maquina))).scalars().one()

    response = await client.delete(f"/costos/maquinas/{maquina.id}")

    assert response.status_code == 422
    assert "BAJA" in response.json()["detail"]
