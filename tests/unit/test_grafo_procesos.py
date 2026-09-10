"""F2 de masa-procesos-y-maquinaria: el grafo de procesos en paralelo.

Ver openspec/changes/masa-procesos-y-maquinaria/{specs/procesos/spec.md,
tasks.md 2.4-2.16} en el repo `panacea-produccion`. F2 no cambia el
comportamiento: el motor viejo sigue generando las órdenes y el grafo sólo se
lee para comparar.
"""

from datetime import date

from sqlalchemy import select

from app.models.insumos import Insumos
from app.models.procesos import Proceso, ProcesoLinea
from app.models.productos import Costos, Productos

FECHA = date(2026, 8, 25)


async def _make_producto(session, **overrides):
    defaults = dict(
        codigo="G1", categoria="PANADERIA", nombre="Producto", utilidad=30, precio_actual=1000,
        unidad_medida="UN", lote_produccion=100, tiempo_produccion=2, responsable="Panaderia",
        is_producto=True, habilitado=True, prioridad=10,
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


async def _make_costo(session, producto, insumo, cantidad):
    session.add(Costos(producto_id=producto.id, insumo_id=insumo.id, cantidad=cantidad))
    await session.commit()


def _payload(**overrides):
    base = dict(
        codigo="PR1", nombre="Masa de francés", tipo="ELABORACION", responsable="Panaderia",
        lote_referencia=162, lote_unidad="KG", lote_minimo=162, lote_multiplo=162, minutos_setup=5,
        lineas=[],
    )
    base.update(overrides)
    return base


def _linea(**overrides):
    base = dict(rol="ENTRADA", insumo_id=None, producto_id=None, cantidad=1, unidad="KG")
    base.update(overrides)
    return base


async def _campos_articulo(session, producto_id):
    """(naturaleza, unidad_base, vendible, peso_unitario_g) leídos de la base.

    Se leen como columnas y no como instancia: recargar el objeto dispara el
    eager-load de `producto_base` (lazy="selectin") fuera del contexto async y
    revienta con MissingGreenlet.
    """
    return (
        await session.execute(
            select(
                Productos.naturaleza, Productos.unidad_base, Productos.vendible, Productos.peso_unitario_g
            ).where(Productos.id == producto_id)
        )
    ).one()


async def _proceso_por_codigo(session, codigo):
    return (
        await session.execute(select(Proceso).where(Proceso.codigo == codigo))
    ).scalars().first()


# ── 2.4 y 2.5 · campos de artículo ──────────────────────────────────────────

async def test_backfill_deriva_naturaleza_y_unidad_base(session, correr_script):
    masa = await _make_producto(session, codigo="GM", nombre="Masa", is_producto=False, unidad_medida="GR")
    pan = await _make_producto(session, codigo="GP", nombre="Pan", is_producto=True, unidad_medida="UN")
    deshabilitado = await _make_producto(session, codigo="GD", nombre="Viejo", habilitado=False)

    await correr_script("backfill_grafo_procesos.sql")

    assert (await _campos_articulo(session, masa.id))[:3] == ("SEMIELABORADO", "KG", False)
    assert (await _campos_articulo(session, pan.id))[:3] == ("TERMINADO", "UN", True)
    # Un terminado deshabilitado no es vendible: no está en el catálogo.
    assert (await _campos_articulo(session, deshabilitado.id))[2] is False


async def test_backfill_no_inventa_peso_unitario(session, correr_script):
    pan = await _make_producto(session, codigo="GP2", unidad_medida="UN")

    await correr_script("backfill_grafo_procesos.sql")

    # El gramaje y el peso unitario son relevamiento de planta (F3), no se
    # pueden deducir de nada que exista hoy.
    assert (await _campos_articulo(session, pan.id))[3] is None


# ── 2.6 · el caso degenerado: un producto que se hace solo ──────────────────

async def test_backfill_crea_proceso_degenerado_para_producto_sin_base(session, correr_script):
    harina = await _make_insumo(session)
    pan = await _make_producto(session, codigo="GS", nombre="Pan solo", lote_produccion=80)
    await _make_costo(session, pan, harina, cantidad=50)

    await correr_script("backfill_grafo_procesos.sql")

    proceso = await _proceso_por_codigo(session, f"ELAB-P{pan.id}")
    assert proceso is not None
    assert (proceso.tipo, proceso.lote_referencia) == ("ELABORACION", 80)

    roles = {linea.rol for linea in proceso.lineas}
    assert roles == {"ENTRADA", "SALIDA"}
    entrada = next(linea for linea in proceso.lineas if linea.rol == "ENTRADA")
    salida = next(linea for linea in proceso.lineas if linea.rol == "SALIDA")
    assert (entrada.insumo_id, entrada.cantidad) == (harina.id, 50)
    assert (salida.producto_id, salida.cantidad) == (pan.id, 80)


# ── 2.7 · la masa con hijos ─────────────────────────────────────────────────

async def test_backfill_crea_division_con_una_salida_por_hijo(session, correr_script):
    harina = await _make_insumo(session)
    masa = await _make_producto(session, codigo="GMB", nombre="Masa", is_producto=False,
                                unidad_medida="GR", lote_produccion=162)
    await _make_costo(session, masa, harina, cantidad=100)
    uno = await _make_producto(session, codigo="GH1", nombre="Largo", producto_base_id=masa.id)
    dos = await _make_producto(session, codigo="GH2", nombre="Baguetín", producto_base_id=masa.id)

    await correr_script("backfill_grafo_procesos.sql")

    division = await _proceso_por_codigo(session, f"DIV-P{masa.id}")
    assert division is not None and division.tipo == "DIVISION"

    entradas = [linea for linea in division.lineas if linea.rol == "ENTRADA"]
    salidas = [linea for linea in division.lineas if linea.rol == "SALIDA"]
    assert [linea.producto_id for linea in entradas] == [masa.id]
    assert sorted(linea.producto_id for linea in salidas) == sorted([uno.id, dos.id])
    # El gramaje es exactamente lo que el modelo viejo no sabía.
    assert all(linea.gramaje_g is None for linea in salidas)


async def test_backfill_usa_transformacion_si_el_hijo_tiene_insumos_propios(session, correr_script):
    harina = await _make_insumo(session, nombre="Harina")
    semillas = await _make_insumo(session, nombre="Semillas")
    masa = await _make_producto(session, codigo="GMT", nombre="Masa molde", is_producto=False,
                                unidad_medida="GR", lote_produccion=120)
    await _make_costo(session, masa, harina, cantidad=100)
    integral = await _make_producto(session, codigo="GI", nombre="Molde integral", producto_base_id=masa.id)
    await _make_costo(session, integral, semillas, cantidad=3)

    await correr_script("backfill_grafo_procesos.sql")

    # Los insumos propios de un hijo no pueden colgar del DIVISION: ese proceso
    # lo comparten todos los hermanos.
    transformacion = await _proceso_por_codigo(session, f"TRANS-P{integral.id}")
    assert transformacion is not None and transformacion.tipo == "TRANSFORMACION"

    entradas = [linea for linea in transformacion.lineas if linea.rol == "ENTRADA"]
    assert [linea.producto_id for linea in entradas if linea.producto_id] == [masa.id]
    assert [linea.insumo_id for linea in entradas if linea.insumo_id] == [semillas.id]

    # Y como el único hijo tenía insumos propios, no hace falta un DIVISION.
    assert await _proceso_por_codigo(session, f"DIV-P{masa.id}") is None


async def test_backfill_es_idempotente(session, correr_script):
    harina = await _make_insumo(session)
    pan = await _make_producto(session, codigo="GID")
    await _make_costo(session, pan, harina, cantidad=50)

    await correr_script("backfill_grafo_procesos.sql")
    await correr_script("backfill_grafo_procesos.sql")

    # Cada INSERT del script está guardado por un NOT EXISTS, así que correrlo
    # de nuevo no crea un segundo proceso ni repite sus líneas.
    procesos = (await session.execute(select(Proceso))).scalars().all()
    assert len(procesos) == 1
    lineas = (await session.execute(select(ProcesoLinea))).scalars().all()
    assert sorted(l.rol for l in lineas) == ["ENTRADA", "SALIDA"]


async def test_backfill_no_pisa_los_gramajes_ya_relevados(session, correr_script):
    """Correrlo de nuevo con parte del relevamiento hecho no borra ese trabajo.

    Importa porque el script se corre varias veces mientras el catálogo se va
    cargando: si cada corrida reseteara los gramajes, el relevamiento de planta
    no terminaría nunca.
    """
    harina = await _make_insumo(session)
    masa = await _make_producto(session, codigo="GNP", nombre="Masa", is_producto=False,
                                unidad_medida="GR", lote_produccion=162)
    await _make_costo(session, masa, harina, cantidad=100)
    hijo = await _make_producto(session, codigo="GNH", nombre="Bollo", producto_base_id=masa.id)

    await correr_script("backfill_grafo_procesos.sql")
    division = await _proceso_por_codigo(session, f"DIV-P{masa.id}")
    salida = next(linea for linea in division.lineas if linea.rol == "SALIDA")
    salida.gramaje_g = 180
    await session.commit()

    await correr_script("backfill_grafo_procesos.sql")

    # Se lee como columna: recargar la instancia después de que el script la
    # tocó por fuera del ORM dispara el eager-load fuera del contexto async.
    gramaje = (
        await session.execute(
            select(ProcesoLinea.gramaje_g).where(ProcesoLinea.id == salida.id)
        )
    ).scalar_one()
    assert gramaje == 180


# ── 2.16 · el grafo reproduce el cálculo viejo ──────────────────────────────

async def test_el_grafo_reproduce_el_escalado_viejo_con_gramajes_iguales(session, correr_script):
    """Cuando todos los hijos pesan lo mismo, los dos motores coinciden.

    Es la única condición en la que el motor viejo es correcto: `Σ cantidad ÷
    lote_produccion` supone que las unidades son homogéneas. El test fija esa
    equivalencia para que el reporte comparativo de F3 tenga un caso conocido
    donde la diferencia tiene que ser cero.
    """
    harina = await _make_insumo(session)
    masa = await _make_producto(session, codigo="GEQ", nombre="Masa", is_producto=False,
                                unidad_medida="GR", lote_produccion=100)
    await _make_costo(session, masa, harina, cantidad=50)
    uno = await _make_producto(session, codigo="GE1", nombre="A", producto_base_id=masa.id)
    dos = await _make_producto(session, codigo="GE2", nombre="B", producto_base_id=masa.id)

    await correr_script("backfill_grafo_procesos.sql")

    division = await _proceso_por_codigo(session, f"DIV-P{masa.id}")
    salidas = [linea for linea in division.lineas if linea.rol == "SALIDA"]

    # Motor viejo: 60 + 40 = 100 unidades, escala 1, harina 50.
    demanda = {uno.id: 60, dos.id: 40}
    escala_vieja = sum(demanda.values()) / masa.lote_produccion

    # Motor nuevo con un gramaje uniforme de 1 kg: 100 kg de masa sobre un lote
    # de 100 kg da la misma escala.
    gramaje_uniforme_kg = 1.0
    masa_requerida = sum(demanda[linea.producto_id] * gramaje_uniforme_kg for linea in salidas)
    escala_nueva = masa_requerida / division.lote_referencia

    assert escala_nueva == escala_vieja == 1.0

    entrada_harina = next(
        linea for linea in (await _proceso_por_codigo(session, f"ELAB-P{masa.id}")).lineas
        if linea.insumo_id == harina.id
    )
    assert entrada_harina.cantidad * escala_nueva == 50


# ── 2.10 · validación que bloquea ───────────────────────────────────────────

async def test_proceso_sin_salida_es_rechazado(client, session):
    harina = await _make_insumo(session)
    payload = _payload(lineas=[_linea(rol="ENTRADA", insumo_id=harina.id, cantidad=100)])

    response = await client.post("/costos/procesos", json=payload)

    assert response.status_code == 422
    assert "SALIDA" in response.json()["detail"]


async def test_lote_minimo_mayor_al_de_referencia_es_rechazado(client, session):
    pan = await _make_producto(session, codigo="GLM")
    payload = _payload(
        lote_referencia=100, lote_minimo=200,
        lineas=[_linea(rol="SALIDA", producto_id=pan.id, cantidad=100)],
    )

    response = await client.post("/costos/procesos", json=payload)

    assert response.status_code == 422
    assert "lote mínimo" in response.json()["detail"]


async def test_linea_sin_articulo_es_rechazada(client, session):
    payload = _payload(lineas=[_linea(rol="SALIDA", cantidad=100)])

    response = await client.post("/costos/procesos", json=payload)

    assert response.status_code == 422
    assert "insumo" in response.json()["detail"]


async def test_linea_con_insumo_y_producto_a_la_vez_es_rechazada(client, session):
    harina = await _make_insumo(session)
    pan = await _make_producto(session, codigo="GXO")
    payload = _payload(
        lineas=[_linea(rol="SALIDA", insumo_id=harina.id, producto_id=pan.id, cantidad=1)]
    )

    response = await client.post("/costos/procesos", json=payload)

    assert response.status_code == 422


# ── 2.9 · ciclos ────────────────────────────────────────────────────────────

async def test_proceso_que_consume_su_propia_salida_es_rechazado(client, session):
    pan = await _make_producto(session, codigo="GC0")
    payload = _payload(
        lineas=[
            _linea(rol="ENTRADA", producto_id=pan.id, cantidad=1),
            _linea(rol="SALIDA", producto_id=pan.id, cantidad=1),
        ]
    )

    response = await client.post("/costos/procesos", json=payload)

    assert response.status_code == 422
    assert "ciclo" in response.json()["detail"].lower()


async def test_ciclo_de_tres_procesos_es_rechazado_con_la_cadena(client, session):
    a = await _make_producto(session, codigo="GCA", nombre="A")
    b = await _make_producto(session, codigo="GCB", nombre="B")
    c = await _make_producto(session, codigo="GCC", nombre="C")

    # A -> B
    primero = await client.post("/costos/procesos", json=_payload(
        codigo="P-AB", nombre="A a B",
        lineas=[_linea(rol="ENTRADA", producto_id=a.id, cantidad=1),
                _linea(rol="SALIDA", producto_id=b.id, cantidad=1)],
    ))
    assert primero.status_code == 201
    # B -> C
    segundo = await client.post("/costos/procesos", json=_payload(
        codigo="P-BC", nombre="B a C",
        lineas=[_linea(rol="ENTRADA", producto_id=b.id, cantidad=1),
                _linea(rol="SALIDA", producto_id=c.id, cantidad=1)],
    ))
    assert segundo.status_code == 201

    # C -> A cierra el ciclo, y la validación de un solo salto no lo vería.
    tercero = await client.post("/costos/procesos", json=_payload(
        codigo="P-CA", nombre="C a A",
        lineas=[_linea(rol="ENTRADA", producto_id=c.id, cantidad=1),
                _linea(rol="SALIDA", producto_id=a.id, cantidad=1)],
    ))

    assert tercero.status_code == 422
    detail = tercero.json()["detail"]
    assert "Ciclo" in detail
    assert "B a C" in detail and "A a B" in detail


async def test_una_cadena_sin_ciclo_se_acepta(client, session):
    a = await _make_producto(session, codigo="GNA", nombre="A")
    b = await _make_producto(session, codigo="GNB", nombre="B")
    c = await _make_producto(session, codigo="GNC", nombre="C")

    primero = await client.post("/costos/procesos", json=_payload(
        codigo="N-AB", nombre="A a B",
        lineas=[_linea(rol="ENTRADA", producto_id=a.id, cantidad=1),
                _linea(rol="SALIDA", producto_id=b.id, cantidad=1)],
    ))
    segundo = await client.post("/costos/procesos", json=_payload(
        codigo="N-BC", nombre="B a C",
        lineas=[_linea(rol="ENTRADA", producto_id=b.id, cantidad=1),
                _linea(rol="SALIDA", producto_id=c.id, cantidad=1)],
    ))

    assert (primero.status_code, segundo.status_code) == (201, 201)


# ── 2.11 y 2.12 · lectura y escritura ───────────────────────────────────────

async def test_get_proceso_devuelve_el_grafo_completo(client, session):
    harina = await _make_insumo(session, nombre="Harina")
    masa = await _make_producto(session, codigo="GGF", nombre="Masa", is_producto=False)
    creado = await client.post("/costos/procesos", json=_payload(
        codigo="G-FULL",
        lineas=[_linea(rol="ENTRADA", insumo_id=harina.id, cantidad=100),
                _linea(rol="SALIDA", producto_id=masa.id, cantidad=162)],
    ))
    assert creado.status_code == 201

    response = await client.get(f"/costos/procesos/{creado.json()['id']}")

    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["codigo"] == "G-FULL"
    assert len(cuerpo["lineas"]) == 2
    # El nombre resuelto: el frontend no tiene que resolver artículos aparte.
    nombres = {linea["insumo_nombre"] or linea["producto_nombre"] for linea in cuerpo["lineas"]}
    assert nombres == {"Harina", "Masa"}


async def test_las_ramas_que_no_suman_el_lote_avisan_sin_bloquear(client, session):
    uno = await _make_producto(session, codigo="GW1", nombre="A")
    dos = await _make_producto(session, codigo="GW2", nombre="B")

    response = await client.post("/costos/procesos", json=_payload(
        codigo="G-WARN", tipo="DIVISION", lote_referencia=162,
        lineas=[_linea(rol="ENTRADA", producto_id=uno.id, cantidad=162),
                _linea(rol="SALIDA", producto_id=dos.id, cantidad=150)],
    ))

    assert response.status_code == 201
    advertencias = response.json()["advertencias"]
    assert any("faltan 12" in aviso for aviso in advertencias)


async def test_el_codigo_vigente_no_se_puede_repetir(client, session):
    pan = await _make_producto(session, codigo="GDUP")
    payload = _payload(codigo="G-DUP", lineas=[_linea(rol="SALIDA", producto_id=pan.id, cantidad=1)])

    primero = await client.post("/costos/procesos", json=payload)
    segundo = await client.post("/costos/procesos", json=payload)

    assert primero.status_code == 201
    assert segundo.status_code == 422


# ── 2.13 · versionado ───────────────────────────────────────────────────────

async def test_editar_un_proceso_no_usado_lo_modifica_en_el_lugar(client, session):
    pan = await _make_producto(session, codigo="GV1")
    creado = await client.post("/costos/procesos", json=_payload(
        codigo="G-V1", lineas=[_linea(rol="SALIDA", producto_id=pan.id, cantidad=1)]))
    proceso_id = creado.json()["id"]

    response = await client.put(f"/costos/procesos/{proceso_id}", json=_payload(
        codigo="G-V1", nombre="Corregido",
        lineas=[_linea(rol="SALIDA", producto_id=pan.id, cantidad=1)]))

    assert response.status_code == 200
    assert response.json()["id"] == proceso_id
    assert response.json()["version"] == 1
    assert response.json()["nombre"] == "Corregido"
    assert len((await session.execute(select(Proceso))).scalars().all()) == 1


async def test_editar_un_proceso_ya_usado_abre_una_version_nueva(client, session):
    from app.models.ordenes_produccion import OrdenProduccion
    from datetime import datetime, timezone

    pan = await _make_producto(session, codigo="GV2")
    creado = await client.post("/costos/procesos", json=_payload(
        codigo="G-V2", lineas=[_linea(rol="SALIDA", producto_id=pan.id, cantidad=1)]))
    proceso_id = creado.json()["id"]

    session.add(OrdenProduccion(
        codigo="260101-01", fecha_fabricacion=FECHA, responsable="Panaderia", estado="FINALIZADA",
        fecha_creacion=datetime.now(timezone.utc), proceso_id=proceso_id,
    ))
    await session.commit()

    response = await client.put(f"/costos/procesos/{proceso_id}", json=_payload(
        codigo="G-V2", nombre="Receta nueva",
        lineas=[_linea(rol="SALIDA", producto_id=pan.id, cantidad=2)]))

    assert response.status_code == 200
    assert response.json()["id"] != proceso_id
    assert response.json()["version"] == 2

    session.expire_all()
    vieja = await session.get(Proceso, proceso_id)
    # La versión que la orden usó queda intacta y cerrada.
    assert vieja.vigente_hasta is not None
    assert vieja.lineas[0].cantidad == 1


async def test_solo_una_version_vigente_por_codigo(client, session):
    from app.models.ordenes_produccion import OrdenProduccion
    from datetime import datetime, timezone

    pan = await _make_producto(session, codigo="GV3")
    creado = await client.post("/costos/procesos", json=_payload(
        codigo="G-V3", lineas=[_linea(rol="SALIDA", producto_id=pan.id, cantidad=1)]))
    session.add(OrdenProduccion(
        codigo="260101-02", fecha_fabricacion=FECHA, responsable="Panaderia", estado="FINALIZADA",
        fecha_creacion=datetime.now(timezone.utc), proceso_id=creado.json()["id"],
    ))
    await session.commit()

    await client.put(f"/costos/procesos/{creado.json()['id']}", json=_payload(
        codigo="G-V3", nombre="v2", lineas=[_linea(rol="SALIDA", producto_id=pan.id, cantidad=1)]))

    listado = await client.get("/costos/procesos")
    codigos = [p["codigo"] for p in listado.json()]
    assert codigos.count("G-V3") == 1

    con_historicas = await client.get("/costos/procesos?incluir_historicas=true")
    assert [p["codigo"] for p in con_historicas.json()].count("G-V3") == 2


async def test_no_se_puede_borrar_un_proceso_ya_usado(client, session):
    from app.models.ordenes_produccion import OrdenProduccion
    from datetime import datetime, timezone

    pan = await _make_producto(session, codigo="GV4")
    creado = await client.post("/costos/procesos", json=_payload(
        codigo="G-V4", lineas=[_linea(rol="SALIDA", producto_id=pan.id, cantidad=1)]))
    session.add(OrdenProduccion(
        codigo="260101-03", fecha_fabricacion=FECHA, responsable="Panaderia", estado="FINALIZADA",
        fecha_creacion=datetime.now(timezone.utc), proceso_id=creado.json()["id"],
    ))
    await session.commit()

    response = await client.delete(f"/costos/procesos/{creado.json()['id']}")

    assert response.status_code == 422


async def test_un_proceso_sin_usar_se_puede_borrar(client, session):
    pan = await _make_producto(session, codigo="GV5")
    creado = await client.post("/costos/procesos", json=_payload(
        codigo="G-V5", lineas=[_linea(rol="SALIDA", producto_id=pan.id, cantidad=1)]))

    response = await client.delete(f"/costos/procesos/{creado.json()['id']}")

    assert response.status_code == 204
    assert (await session.execute(select(ProcesoLinea))).scalars().all() == []
