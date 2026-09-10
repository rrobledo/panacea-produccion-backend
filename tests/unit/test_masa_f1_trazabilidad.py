"""F1 de masa-procesos-y-maquinaria: trazabilidad de la orden y unicidad de la
Programación.

Ver openspec/changes/masa-procesos-y-maquinaria/tasks.md 1.3, 1.4, 1.6 y 1.7 en
el repo `panacea-produccion`. Todo lo de F1 tiene que ser invisible para la
operación: las cantidades de insumo no cambian, sólo se agrega trazabilidad.
"""

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models.insumos import Insumos
from app.models.ordenes_produccion import OrdenProduccion, OrdenProduccionProductoLinea
from app.models.productos import Costos, Productos
from app.models.programacion import Programacion
from app.models.stock_movimiento import StockMovimiento

FECHA = date(2026, 8, 25)


async def _make_producto(session, **overrides):
    defaults = dict(
        codigo="F1", categoria="PANADERIA", nombre="Producto", utilidad=30, precio_actual=1000,
        unidad_medida="UN", lote_produccion=100, tiempo_produccion=2, responsable="Todos",
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


async def _make_programacion(session, producto, fecha, plan, responsable="Panaderia", prod=None):
    row = Programacion(
        fecha=fecha, producto_id=producto.id, producto_nombre=producto.nombre,
        responsable=responsable, plan=plan, prod=prod,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


# ── 1.3 · La línea de producto guarda de qué fila de Programación salió ──────

async def test_generar_guarda_programacion_id_en_la_linea(client, session):
    harina = await _make_insumo(session)
    producto = await _make_producto(session, codigo="F1A", nombre="Pan")
    await _make_costo(session, producto, harina, cantidad=50)
    fila = await _make_programacion(session, producto, FECHA, plan=100)

    response = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    assert response.status_code == 201

    lineas = (await session.execute(select(OrdenProduccionProductoLinea))).scalars().all()
    assert len(lineas) == 1
    assert lineas[0].programacion_id == fila.id


async def test_cada_linea_apunta_a_su_propia_fila(client, session):
    harina = await _make_insumo(session)
    masa = await _make_producto(session, codigo="F1M", nombre="Masa", is_producto=False)
    await _make_costo(session, masa, harina, cantidad=50)
    uno = await _make_producto(session, codigo="F1B", nombre="Pan A", producto_base_id=masa.id)
    dos = await _make_producto(session, codigo="F1C", nombre="Pan B", producto_base_id=masa.id)
    fila_uno = await _make_programacion(session, uno, FECHA, plan=60)
    fila_dos = await _make_programacion(session, dos, FECHA, plan=40)

    response = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    assert response.status_code == 201

    lineas = (await session.execute(select(OrdenProduccionProductoLinea))).scalars().all()
    por_producto = {linea.producto_id: linea.programacion_id for linea in lineas}
    assert por_producto == {uno.id: fila_uno.id, dos.id: fila_dos.id}


# ── 1.4 · Los movimientos de stock referencian la orden por clave foránea ────

async def test_reserva_lleva_orden_id(client, session):
    harina = await _make_insumo(session)
    producto = await _make_producto(session, codigo="F1D", nombre="Pan")
    await _make_costo(session, producto, harina, cantidad=50)
    await _make_programacion(session, producto, FECHA, plan=100)

    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})

    orden = (await session.execute(select(OrdenProduccion))).scalars().one()
    movimientos = (await session.execute(select(StockMovimiento))).scalars().all()
    assert [m.tipo for m in movimientos] == ["RESERVA"]
    assert movimientos[0].orden_id == orden.id
    # `referencia` sigue guardando el código hasta que nadie la lea (task 8.5)
    assert movimientos[0].referencia == orden.codigo


async def test_consumo_lleva_orden_id(client, session):
    harina = await _make_insumo(session)
    producto = await _make_producto(session, codigo="F1E", nombre="Pan")
    await _make_costo(session, producto, harina, cantidad=50)
    await _make_programacion(session, producto, FECHA, plan=100)
    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    orden = (await session.execute(select(OrdenProduccion))).scalars().one()

    response = await client.post(f"/costos/ordenes-produccion/{orden.id}/iniciar")
    assert response.status_code == 200

    consumos = (
        await session.execute(select(StockMovimiento).where(StockMovimiento.tipo == "CONSUMO"))
    ).scalars().all()
    assert len(consumos) == 1
    assert consumos[0].orden_id == orden.id


async def test_borrar_la_orden_no_deja_movimientos_huerfanos(client, session):
    harina = await _make_insumo(session)
    producto = await _make_producto(session, codigo="F1F", nombre="Pan")
    await _make_costo(session, producto, harina, cantidad=50)
    await _make_programacion(session, producto, FECHA, plan=100)
    await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    orden = (await session.execute(select(OrdenProduccion))).scalars().one()

    response = await client.delete(f"/costos/ordenes-produccion/{orden.id}")
    assert response.status_code == 204

    session.expire_all()
    assert (await session.execute(select(StockMovimiento))).scalars().all() == []


# ── 1.6 · Una sola fila de Programación por producto y fecha ─────────────────

async def test_segunda_fila_para_el_mismo_producto_y_fecha_falla(session):
    producto = await _make_producto(session, codigo="F1G", nombre="Pan")
    await _make_programacion(session, producto, FECHA, plan=100)

    session.add(
        Programacion(
            fecha=FECHA, producto_id=producto.id, producto_nombre=producto.nombre,
            responsable="Panaderia", plan=50, prod=None,
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_el_indice_no_alcanza_a_las_filas_sin_producto_ni_fecha(session):
    # El índice es parcial a propósito: las filas sin producto o sin fecha no
    # son programación real y pueden repetirse.
    session.add(Programacion(fecha=None, producto_id=None, responsable="Panaderia", plan=1, prod=None))
    session.add(Programacion(fecha=None, producto_id=None, responsable="Panaderia", plan=2, prod=None))
    await session.commit()

    filas = (await session.execute(select(Programacion))).scalars().all()
    assert len(filas) == 2


# ── 1.5 · La reconciliación de duplicados ────────────────────────────────────

INDICE_UNICO = """
CREATE UNIQUE INDEX IF NOT EXISTS costos_programacion_producto_fecha_key
    ON costos_programacion (producto_id, fecha)
 WHERE producto_id IS NOT NULL AND fecha IS NOT NULL
"""


@pytest_asyncio.fixture
async def sin_indice_unico(session):
    """Permite insertar los duplicados que el script tiene que limpiar.

    El índice de la migración 0027 impide justamente crear el estado que
    el script repara, así que se lo quita mientras dura el test. El teardown
    vacía la tabla y lo repone, para no dejar el esquema del contenedor de
    tests a medias para el resto de la suite.
    """
    await session.execute(text("DROP INDEX IF EXISTS costos_programacion_producto_fecha_key"))
    await session.commit()
    yield
    await session.rollback()
    await session.execute(text("DELETE FROM costos_programacion"))
    await session.execute(text(INDICE_UNICO))
    await session.commit()


async def _crear_indice_unico(session) -> None:
    """Crear el índice es la verificación real de que no quedaron duplicados."""
    await session.execute(text(INDICE_UNICO))
    await session.commit()


async def test_dedupe_suma_plan_y_prod_y_conserva_la_fila_de_menor_id(session, sin_indice_unico, correr_script):
    producto = await _make_producto(session, codigo="F1H", nombre="Pan")
    await session.execute(
        Programacion.__table__.insert(),
        [
            dict(fecha=FECHA, producto_id=producto.id, producto_nombre="Pan", responsable="Panaderia", plan=10, prod=3),
            dict(fecha=FECHA, producto_id=producto.id, producto_nombre="Pan", responsable="Panaderia", plan=5, prod=None),
        ],
    )
    await session.commit()

    await correr_script("dedupe_programacion.sql")

    session.expire_all()
    filas = (await session.execute(select(Programacion).order_by(Programacion.id))).scalars().all()
    assert len(filas) == 1
    assert (filas[0].plan, filas[0].prod) == (15, 3)
    await _crear_indice_unico(session)


async def test_dedupe_conserva_el_responsable_de_la_fila_que_sobrevive(session, sin_indice_unico, correr_script):
    producto = await _make_producto(session, codigo="F1I", nombre="Pan")
    await session.execute(
        Programacion.__table__.insert(),
        [
            dict(fecha=FECHA, producto_id=producto.id, producto_nombre="Pan", responsable="Panaderia", plan=10, prod=None),
            dict(fecha=FECHA, producto_id=producto.id, producto_nombre="Pan", responsable="Pasteleria", plan=5, prod=None),
        ],
    )
    await session.commit()

    await correr_script("dedupe_programacion.sql")

    session.expire_all()
    fila = (await session.execute(select(Programacion))).scalars().one()
    # Se conserva el responsable de la fila de menor id; el script además lo
    # reporta como `responsables_distintos` para que alguien lo mire.
    assert fila.responsable == "Panaderia"
    assert fila.plan == 15
    await _crear_indice_unico(session)


async def test_dedupe_deja_la_tabla_lista_para_el_indice_unico(session, sin_indice_unico, correr_script):
    producto = await _make_producto(session, codigo="F1J", nombre="Pan")
    await session.execute(
        Programacion.__table__.insert(),
        [
            dict(fecha=FECHA, producto_id=producto.id, producto_nombre="Pan", responsable="Panaderia", plan=10, prod=None),
            dict(fecha=FECHA, producto_id=producto.id, producto_nombre="Pan", responsable="Panaderia", plan=5, prod=None),
        ],
    )
    await session.commit()

    await correr_script("dedupe_programacion.sql")

    # La verificación real del script: después de correrlo el índice único se
    # puede crear. Si hubiera dejado un duplicado, esto falla.
    session.expire_all()
    await _crear_indice_unico(session)
    filas = (await session.execute(select(Programacion))).scalars().all()
    assert len(filas) == 1


# ── 1.7 · F1 no cambia ninguna cantidad de insumo ────────────────────────────

async def test_las_cantidades_de_insumo_no_cambian(client, session):
    """Los mismos números que producía el motor antes de F1.

    `cantidad_total / lote_produccion × costo.cantidad`, redondeado half-up
    sobre el total acumulado (preview-generacion-ordenes/design.md:53-61):
    (60 + 40) / 100 × 50 = 50 de harina, 100 / 100 × 3 = 3 de sal.
    """
    harina = await _make_insumo(session, nombre="Harina")
    sal = await _make_insumo(session, nombre="Sal")
    masa = await _make_producto(session, codigo="F1K", nombre="Masa", is_producto=False, lote_produccion=100)
    await _make_costo(session, masa, harina, cantidad=50)
    await _make_costo(session, masa, sal, cantidad=3)
    uno = await _make_producto(session, codigo="F1L", nombre="Pan A", producto_base_id=masa.id)
    dos = await _make_producto(session, codigo="F1M2", nombre="Pan B", producto_base_id=masa.id)
    await _make_programacion(session, uno, FECHA, plan=60)
    await _make_programacion(session, dos, FECHA, plan=40)

    response = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    assert response.status_code == 201

    ordenes = response.json()
    assert len(ordenes) == 1
    cantidades = {linea["insumo_nombre"]: linea["cantidad"] for linea in ordenes[0]["insumos"]}
    assert cantidades == {"Harina": 50, "Sal": 3}
