"""Finalizar una orden escribe el ejecutado en la Programación (columna E)."""
from datetime import date

import pytest
from sqlalchemy import select

from app.models.insumos import Insumos
from app.models.ordenes_produccion import OrdenProduccion, OrdenProduccionProductoLinea, ProductoFabricado
from app.models.planificacion import Planificacion
from app.models.productos import Costos, Productos
from app.models.programacion import Programacion
from app.schemas.ordenes_produccion import FinalizarLineaRequest, FinalizarOrdenRequest
from app.services import ordenes_produccion_service

FECHA = date(2026, 8, 25)
OTRA_FECHA = date(2026, 8, 26)


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


async def _programar(session, producto, plan, responsable="Panaderia", fecha=FECHA, prod=None):
    row = Programacion(fecha=fecha, producto_id=producto.id, producto_nombre=producto.nombre,
                       responsable=responsable, plan=plan, prod=prod)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def _ubicacion(client, nombre="Depósito"):
    r = await client.post("/costos/ubicaciones", json={"nombre": nombre})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def _generar_e_iniciar(client, fecha=FECHA):
    generar = await client.post("/costos/ordenes-produccion/generar", json={"fecha": fecha.isoformat()})
    assert generar.status_code == 201, generar.text
    orden = generar.json()[0]
    iniciar = await client.post(f"/costos/ordenes-produccion/{orden['id']}/iniciar")
    assert iniciar.status_code == 200, iniciar.text
    return orden


async def _finalizar(client, orden_id, lineas):
    return await client.post(f"/costos/ordenes-produccion/{orden_id}/finalizar", json={"lineas": lineas})


async def _prod(session, producto_id, fecha=FECHA):
    """Lee `prod` de la fila de Programación con un select de columna.

    De columna y no de entidad a propósito: el valor viene de la base y no de
    la caché de identidad de la sesión.
    """
    result = await session.execute(
        select(Programacion.prod)
        .where(Programacion.producto_id == producto_id, Programacion.fecha == fecha)
        .order_by(Programacion.id)
    )
    return result.scalars().first()


async def test_finalizar_escribe_la_cantidad_fabricada_en_la_programacion(client, session):
    """4.1 / 4.2 — el ejecutado incluye la orden que se está cerrando.

    Es la propiedad que hay que fijar: si las filas nuevas y el estado recién
    asignado no llegaran a la base antes del agregado, `prod` quedaría en el
    total anterior (0 en el caso normal) sin que nada falle. Verificado que el
    test cubre el resultado y no el mecanismo: sacando el `flush` explícito de
    `finalizar_orden` sigue pasando, porque el autoflush de SQLAlchemy manda las
    pendientes igual al ejecutar el SELECT (design.md Decision 5).
    """
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    fila = await _programar(session, pan, plan=100)
    assert fila.prod is None

    orden = await _generar_e_iniciar(client)
    ubicacion = await _ubicacion(client)

    respuesta = await _finalizar(client, orden["id"], [
        {"producto_id": pan.id, "cantidad_fabricada": 95, "ubicacion_id": ubicacion},
    ])
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "FINALIZADA"

    assert await _prod(session, pan.id) == 95


async def test_la_fecha_es_la_de_fabricacion_no_la_del_cierre(client, session):
    """4.3 — imputa el día que la orden dice fabricar, no el día del cierre.

    `ProductoFabricado.fecha` es `datetime.now`, así que una orden de FECHA
    cerrada hoy tiene que escribir la fila de FECHA y no la de hoy (Decision 2).
    """
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, plan=100, fecha=FECHA)
    hoy = date.today()
    await _programar(session, pan, plan=50, fecha=hoy)

    orden = await _generar_e_iniciar(client, fecha=FECHA)
    ubicacion = await _ubicacion(client)
    respuesta = await _finalizar(client, orden["id"], [
        {"producto_id": pan.id, "cantidad_fabricada": 80, "ubicacion_id": ubicacion},
    ])
    assert respuesta.status_code == 200, respuesta.text

    assert await _prod(session, pan.id, fecha=FECHA) == 80
    assert await _prod(session, pan.id, fecha=hoy) is None


async def test_el_desperdicio_no_entra_en_el_ejecutado(client, session):
    """4.4 — E cuenta lo fabricado bueno; el desperdicio queda en su registro."""
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, plan=100)

    orden = await _generar_e_iniciar(client)
    ubicacion = await _ubicacion(client)
    compost = await _ubicacion(client, "Compost")

    respuesta = await _finalizar(client, orden["id"], [
        {
            "producto_id": pan.id,
            "cantidad_fabricada": 90,
            "ubicacion_id": ubicacion,
            "cantidad_desperdicio": 10,
            "ubicacion_desperdicio_id": compost,
            "motivo_desperdicio": "Se quemó una tanda",
        },
    ])
    assert respuesta.status_code == 200, respuesta.text

    assert await _prod(session, pan.id) == 90  # no 100

    fabricados = await client.get("/costos/productos_fabricados")
    assert [(f["cantidad_fabricada"], f["cantidad_desperdicio"]) for f in fabricados.json()] == [(90, 10)]


async def test_el_valor_cargado_a_mano_queda_reemplazado(client, session):
    """4.5 — lo fabricado manda sobre lo transcripto a mano (Decision 1)."""
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, plan=100, prod=70)

    orden = await _generar_e_iniciar(client)
    ubicacion = await _ubicacion(client)
    respuesta = await _finalizar(client, orden["id"], [
        {"producto_id": pan.id, "cantidad_fabricada": 88, "ubicacion_id": ubicacion},
    ])
    assert respuesta.status_code == 200, respuesta.text

    assert await _prod(session, pan.id) == 88


async def test_sincronizar_dos_veces_no_duplica_el_ejecutado(client, session):
    """4.6 — la sincronización es idempotente: asigna el total, no incrementa.

    Importa porque `prod` se suma en los reportes (`analytics_service`), donde un
    valor duplicado no se nota hasta que alguien audita el mes (Decision 1).
    """
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, plan=100)

    orden = await _generar_e_iniciar(client)
    ubicacion = await _ubicacion(client)
    respuesta = await _finalizar(client, orden["id"], [
        {"producto_id": pan.id, "cantidad_fabricada": 95, "ubicacion_id": ubicacion},
    ])
    assert respuesta.status_code == 200, respuesta.text
    assert await _prod(session, pan.id) == 95

    await ordenes_produccion_service.sincronizar_ejecutado_programacion(session, FECHA, [pan.id])
    await session.commit()

    assert await _prod(session, pan.id) == 95  # no 190


async def test_dos_lineas_del_mismo_producto_suman_una_sola_vez(client, session):
    """4.7 — una orden puede tener dos líneas del mismo producto.

    Pasa cuando el mismo producto tiene dos filas de Programación en el mismo
    grupo (ver `preview-generacion-ordenes`, Decision 3). El total sale del
    agregado sobre `productos_fabricados`, así que las dos líneas suman sin
    escribirse dos veces.
    """
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, plan=100, responsable="Panaderia")

    orden = await _generar_e_iniciar(client)
    ubicacion = await _ubicacion(client)

    # Segunda línea del mismo producto en la misma orden, como la armaría una
    # Programación con dos filas del producto en el grupo.
    session.add(OrdenProduccionProductoLinea(orden_id=orden["id"], producto_id=pan.id, cantidad_planeada=40))
    await session.commit()

    respuesta = await _finalizar(client, orden["id"], [
        {"producto_id": pan.id, "cantidad_fabricada": 60, "ubicacion_id": ubicacion},
        {"producto_id": pan.id, "cantidad_fabricada": 35, "ubicacion_id": ubicacion},
    ])
    assert respuesta.status_code == 200, respuesta.text

    assert await _prod(session, pan.id) == 95


async def test_cantidad_fraccionaria_se_redondea_half_up(client, session):
    """4.8 — `prod` es INTEGER: el total se redondea con ROUND_HALF_UP.

    10.5 tiene que dar 11 y no 10, que es lo que devolvería el `round()` de
    Python por banker's rounding (Decision 4).
    """
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, plan=100)

    orden = await _generar_e_iniciar(client)
    ubicacion = await _ubicacion(client)
    respuesta = await _finalizar(client, orden["id"], [
        {"producto_id": pan.id, "cantidad_fabricada": 10.5, "ubicacion_id": ubicacion},
    ])
    assert respuesta.status_code == 200, respuesta.text

    assert await _prod(session, pan.id) == 11


async def test_sin_fila_de_programacion_la_orden_se_finaliza_igual(client, session):
    """4.9 — la sincronización no puede bloquear el cierre (Decision 6)."""
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    fila = await _programar(session, pan, plan=100)

    orden = await _generar_e_iniciar(client)
    ubicacion = await _ubicacion(client)

    # La fila de Programación desaparece después de generada la orden.
    await session.delete(fila)
    await session.commit()

    respuesta = await _finalizar(client, orden["id"], [
        {"producto_id": pan.id, "cantidad_fabricada": 95, "ubicacion_id": ubicacion},
    ])
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "FINALIZADA"

    fabricados = await client.get("/costos/productos_fabricados")
    assert [f["cantidad_fabricada"] for f in fabricados.json()] == [95]


async def test_las_ordenes_no_finalizadas_no_aportan_al_ejecutado(client, session):
    """4.10 — solo `FINALIZADA` cuenta: una asignada o en producción no."""
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, plan=100)

    # Orden generada e iniciada, pero sin finalizar.
    await _generar_e_iniciar(client)
    await ordenes_produccion_service.sincronizar_ejecutado_programacion(session, FECHA, [pan.id])
    await session.commit()
    assert await _prod(session, pan.id) == 0

    result = await session.execute(select(OrdenProduccion.estado))
    assert result.scalars().all() == ["EN_PRODUCCION"]


async def test_finalizar_no_toca_plan_responsable_ni_otras_fechas(client, session):
    """4.11 — la sincronización escribe solo `prod`, y solo en su fila."""
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, plan=100, responsable="Panaderia", fecha=FECHA)
    await _programar(session, pan, plan=50, responsable="Panaderia", fecha=OTRA_FECHA, prod=40)

    orden = await _generar_e_iniciar(client, fecha=FECHA)
    ubicacion = await _ubicacion(client)
    respuesta = await _finalizar(client, orden["id"], [
        {"producto_id": pan.id, "cantidad_fabricada": 95, "ubicacion_id": ubicacion},
    ])
    assert respuesta.status_code == 200, respuesta.text

    filas = (
        await session.execute(
            select(Programacion.fecha, Programacion.plan, Programacion.prod, Programacion.responsable)
            .where(Programacion.producto_id == pan.id)
            .order_by(Programacion.fecha)
        )
    ).all()
    por_fecha = {fila.fecha: fila for fila in filas}
    assert por_fecha[FECHA].plan == 100
    assert por_fecha[FECHA].responsable == "Panaderia"
    assert por_fecha[FECHA].prod == 95
    # La otra fecha del mismo producto queda intacta.
    assert por_fecha[OTRA_FECHA].plan == 50
    assert por_fecha[OTRA_FECHA].prod == 40


async def test_un_fallo_de_la_sincronizacion_no_deja_nada_persistido(client, session, monkeypatch):
    """3.4 — la sincronización va en la misma transacción que la finalización.

    Se llama al servicio directo y no por HTTP porque el fixture `client`
    comparte su sesión con el router: la sesión del test nunca se cierra, así
    que las escrituras pendientes seguirían visibles y el test no probaría
    nada. En producción cada request tiene su sesión y `get_session`
    (`app/db.py`) la cierra con `async with`, que descarta lo no commiteado.
    Lo que este test fija es la propiedad de la que eso depende: que
    `finalizar_orden` no commitea antes de sincronizar, así que un rollback
    posterior al fallo se lleva también el estado y los ProductoFabricado
    (design.md Decision 5).
    """
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, plan=100)

    generada = await _generar_e_iniciar(client)
    ubicacion_id = await _ubicacion(client)
    # El rollback de más abajo expira los objetos de la sesión, así que después
    # `pan.id` intentaría recargarse (MissingGreenlet): se guardan antes.
    pan_id, orden_id = pan.id, generada["id"]

    async def explota(*args, **kwargs):
        raise RuntimeError("fallo simulado al sincronizar la Programación")

    monkeypatch.setattr(ordenes_produccion_service, "sincronizar_ejecutado_programacion", explota)

    orden = await ordenes_produccion_service.get_orden(session, orden_id)
    payload = FinalizarOrdenRequest(
        lineas=[FinalizarLineaRequest(producto_id=pan_id, cantidad_fabricada=95, ubicacion_id=ubicacion_id)]
    )
    with pytest.raises(RuntimeError):
        await ordenes_produccion_service.finalizar_orden(session, orden, payload)

    await session.rollback()

    estado = (
        await session.execute(select(OrdenProduccion.estado).where(OrdenProduccion.id == orden_id))
    ).scalar_one()
    assert estado == "EN_PRODUCCION"
    fabricados = (await session.execute(select(ProductoFabricado.id))).scalars().all()
    assert fabricados == []
    assert await _prod(session, pan_id) is None


async def test_el_grid_de_programacion_muestra_y_deja_editar_el_ejecutado(client, session):
    """5.2 / 5.3 — la columna E del grid ya sirve tal como está.

    El frontend solo renderiza lo que devuelven estos dos endpoints, así que la
    verificación real es acá: `GET /costos/programacion` pivotea `prod` en
    `YYYYMMDD-E`, las columnas lo marcan editable, y el POST lo sigue guardando
    a mano (spec `planning-programacion`).
    """
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    await _programar(session, pan, plan=100)

    orden = await _generar_e_iniciar(client)
    ubicacion = await _ubicacion(client)
    respuesta = await _finalizar(client, orden["id"], [
        {"producto_id": pan.id, "cantidad_fabricada": 95, "ubicacion_id": ubicacion},
    ])
    assert respuesta.status_code == 200, respuesta.text

    campo_e = f"{FECHA.strftime('%Y%m%d')}-E"
    filas = await client.get("/costos/programacion", params={"anio": FECHA.year, "mes": FECHA.month, "semana": 0})
    assert filas.status_code == 200, filas.text
    fila = next(f for f in filas.json() if f["id"] == pan.id)
    assert fila[campo_e] == 95

    columnas = await client.get(
        "/costos/programacion_columnas", params={"anio": FECHA.year, "mes": FECHA.month, "semana": 0}
    )

    def _hojas(nodos):
        for nodo in nodos:
            if nodo.get("children"):
                yield from _hojas(nodo["children"])
            else:
                yield nodo

    columna_e = next(c for c in _hojas(columnas.json()) if c.get("field") == campo_e)
    assert columna_e["editable"] is True

    # Y una corrección a mano sigue guardándose como antes.
    guardar = await client.post("/costos/programacion", json=[{"id": pan.id, campo_e: 92}])
    assert guardar.status_code == 204, guardar.text
    assert await _prod(session, pan.id) == 92


async def test_recorrido_completo_programacion_orden_y_reporte(client, session):
    """6.3 / 6.4 / 6.5 / 6.6 — el recorrido completo, por los endpoints reales.

    Programación con P cargado → generar → iniciar → finalizar con desperdicio y
    con una cantidad distinta de la planeada → E en el grid → reporte de
    Producción. Y se comprueba que la única fila de Programación que cambió es
    la de `(producto_id, fecha_fabricacion)`.
    """
    harina = await _insumo(session)
    pan = await _producto(session, "P1", "Pan")
    await _receta(session, pan, harina)
    # El reporte de Producción saca el planeado de `costos_planificacion`
    # (`max(corregido)` del mes) y descarta las categorías con planeado 0.
    session.add(Planificacion(fecha=date(FECHA.year, FECHA.month, 1), producto_id=pan.id, plan=100, corregido=100))
    await _programar(session, pan, plan=100, fecha=FECHA)
    await _programar(session, pan, plan=60, fecha=OTRA_FECHA)
    await session.commit()

    orden = await _generar_e_iniciar(client, fecha=FECHA)
    ubicacion = await _ubicacion(client)
    compost = await _ubicacion(client, "Compost")

    respuesta = await _finalizar(client, orden["id"], [
        {
            "producto_id": pan.id,
            "cantidad_fabricada": 95,  # distinta de las 100 planeadas
            "ubicacion_id": ubicacion,
            "cantidad_desperdicio": 5,
            "ubicacion_desperdicio_id": compost,
            "motivo_desperdicio": "Se quemó una tanda",
        },
    ])
    assert respuesta.status_code == 200, respuesta.text

    # El grid muestra E en el día correcto, y solo en ese.
    campo_e = f"{FECHA.strftime('%Y%m%d')}-E"
    campo_e_otra = f"{OTRA_FECHA.strftime('%Y%m%d')}-E"
    filas = await client.get("/costos/programacion", params={"anio": FECHA.year, "mes": FECHA.month, "semana": 0})
    fila = next(f for f in filas.json() if f["id"] == pan.id)
    assert fila[campo_e] == 95
    assert fila[campo_e_otra] is None

    # 6.5 — en la base, la única fila con `prod` escrito es la de la fecha de
    # fabricación de la orden.
    escritas = (
        await session.execute(
            select(Programacion.fecha, Programacion.prod, Programacion.plan).order_by(Programacion.fecha)
        )
    ).all()
    assert [(f.fecha, f.prod, f.plan) for f in escritas] == [(FECHA, 95, 100), (OTRA_FECHA, None, 60)]

    # 6.6 — el reporte de Producción (`sum(prod)`) refleja lo ejecutado: 95 de
    # 100 planeadas es el 95%, y el desperdicio no infla el número.
    reporte = await client.get("/costos/get_produccion_by_category", params={"anio": FECHA.year, "mes": FECHA.month})
    assert reporte.status_code == 200, reporte.text
    categoria = next(r for r in reporte.json() if r["categoria"] == "PANADERIA")
    assert categoria["planeado"] == 100
    assert categoria["producido"] == 95
    assert categoria["porcentaje_ejecutado"] == 95.0

    # El desperdicio sigue estando, aparte, en su propio registro.
    fabricados = await client.get("/costos/productos_fabricados")
    assert [(f["cantidad_fabricada"], f["cantidad_desperdicio"]) for f in fabricados.json()] == [(95, 5)]
