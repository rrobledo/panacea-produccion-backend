from datetime import date

from sqlalchemy import func, select

from app.models.insumos import Insumos
from app.models.ordenes_produccion import OrdenProduccion, OrdenProduccionProductoLinea
from app.models.productos import Costos, Productos
from app.models.programacion import Programacion
from app.models.stock_movimiento import StockMovimiento

FECHA = date(2026, 8, 25)


async def _make_producto(session, **overrides):
    defaults = dict(
        codigo="P1", categoria="PANADERIA", nombre="Producto", utilidad=30, precio_actual=1000,
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


async def _make_programacion(session, producto, fecha, plan, responsable="Panaderia"):
    row = Programacion(
        fecha=fecha, producto_id=producto.id, producto_nombre=producto.nombre,
        responsable=responsable, plan=plan, prod=None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def _count(session, model):
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


# ── El preview no persiste nada ──────────────────────────────────────────────

async def test_preview_does_not_persist_anything(client, session):
    harina = await _make_insumo(session)
    producto = await _make_producto(session, codigo="PV1", nombre="Pan")
    await _make_costo(session, producto, harina, cantidad=50)
    await _make_programacion(session, producto, FECHA, plan=100)

    response = await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})
    assert response.status_code == 200
    assert len(response.json()["ordenes"]) == 1

    assert await _count(session, OrdenProduccion) == 0
    assert await _count(session, OrdenProduccionProductoLinea) == 0
    assert await _count(session, StockMovimiento) == 0


async def test_preview_exposes_lote_and_totals(client, session):
    harina = await _make_insumo(session)
    producto = await _make_producto(session, codigo="PV2", nombre="Pan2", lote_produccion=250)
    await _make_costo(session, producto, harina, cantidad=50)
    fila = await _make_programacion(session, producto, FECHA, plan=100)

    orden = (await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})).json()["ordenes"][0]

    assert orden["lote_produccion"] == 250
    assert orden["cantidad_total"] == 100          # por debajo del lote: el front lo marca en rojo
    assert orden["responsable"] == "Panaderia"
    assert orden["producto_base_id"] == producto.id
    linea = orden["productos"][0]
    assert linea["programacion_id"] == fila.id
    assert linea["cantidad_programada"] == 100
    assert linea["cantidad_planeada"] == 100
    assert orden["insumos"][0]["insumo_nombre"] == "Harina"
    assert orden["insumos"][0]["insumo_unidad_medida"] == "KG"


async def test_preview_de_fecha_ya_generada_no_falla_y_reporta_las_existentes(client, session):
    producto = await _make_producto(session, codigo="PV3", nombre="Pan3")
    await _make_programacion(session, producto, FECHA, plan=10)

    assert (await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})).status_code == 201

    response = await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})
    assert response.status_code == 200
    cuerpo = response.json()
    assert cuerpo["ordenes"] == []           # nada pendiente
    assert cuerpo["ordenes_existentes"] == 1  # pero la fecha ya tiene una


async def test_preview_empty_when_nothing_programmed(client, session):
    response = await client.post("/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat()})
    assert response.status_code == 200
    assert response.json()["ordenes"] == []
    assert response.json()["ordenes_existentes"] == 0


# ── Preview y generación coinciden ───────────────────────────────────────────

async def test_preview_and_generar_produce_identical_quantities(client, session):
    harina = await _make_insumo(session, nombre="Harina")
    dulce = await _make_insumo(session, nombre="Dulce")
    masa = await _make_producto(session, codigo="PVM", nombre="Masa", is_producto=False, lote_produccion=100)
    await _make_costo(session, masa, harina, cantidad=50)
    medialuna = await _make_producto(session, codigo="PVF", nombre="Medialuna", producto_base_id=masa.id, lote_produccion=100)
    await _make_costo(session, medialuna, dulce, cantidad=20)
    fila = await _make_programacion(session, medialuna, FECHA, plan=100, responsable="Pasteleria")

    overrides = {"cantidades": [{"programacion_id": fila.id, "cantidad": 137}]}

    preview = (await client.post(
        "/costos/ordenes-produccion/preview", json={"fecha": FECHA.isoformat(), **overrides}
    )).json()["ordenes"][0]
    generada = (await client.post(
        "/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat(), **overrides}
    )).json()[0]

    assert {i["insumo_id"]: i["cantidad"] for i in preview["insumos"]} == \
           {i["insumo_id"]: i["cantidad"] for i in generada["insumos"]}
    assert [p["cantidad_planeada"] for p in preview["productos"]] == \
           [p["cantidad_planeada"] for p in generada["productos"]]


# ── Overrides ────────────────────────────────────────────────────────────────

async def test_generar_uses_override_and_leaves_programacion_untouched(client, session):
    harina = await _make_insumo(session)
    producto = await _make_producto(session, codigo="PV4", nombre="Pan4", lote_produccion=100)
    await _make_costo(session, producto, harina, cantidad=50)
    fila = await _make_programacion(session, producto, FECHA, plan=100)

    response = await client.post(
        "/costos/ordenes-produccion/generar",
        json={"fecha": FECHA.isoformat(), "cantidades": [{"programacion_id": fila.id, "cantidad": 200}]},
    )
    assert response.status_code == 201
    orden = response.json()[0]

    assert orden["productos"][0]["cantidad_planeada"] == 200
    assert orden["insumos"][0]["cantidad"] == 100  # 200/100 * 50

    await session.refresh(fila)
    assert fila.plan == 100  # la Programación no se toca (design.md / propuesta)


async def test_override_zero_excludes_the_linea(client, session):
    harina = await _make_insumo(session)
    masa = await _make_producto(session, codigo="PVM2", nombre="Masa2", is_producto=False, lote_produccion=100)
    await _make_costo(session, masa, harina, cantidad=50)
    p1 = await _make_producto(session, codigo="PVA", nombre="A", producto_base_id=masa.id, lote_produccion=100)
    p2 = await _make_producto(session, codigo="PVB", nombre="B", producto_base_id=masa.id, lote_produccion=100)
    fila1 = await _make_programacion(session, p1, FECHA, plan=100, responsable="Pasteleria")
    await _make_programacion(session, p2, FECHA, plan=100, responsable="Pasteleria")

    orden = (await client.post(
        "/costos/ordenes-produccion/generar",
        json={"fecha": FECHA.isoformat(), "cantidades": [{"programacion_id": fila1.id, "cantidad": 0}]},
    )).json()[0]

    assert [p["producto_id"] for p in orden["productos"]] == [p2.id]
    assert orden["insumos"][0]["cantidad"] == 50  # solo los 100 de p2


async def test_group_left_without_lineas_generates_no_orden(client, session):
    harina = await _make_insumo(session)
    solo = await _make_producto(session, codigo="PVC", nombre="Solo", lote_produccion=100)
    await _make_costo(session, solo, harina, cantidad=50)
    otro = await _make_producto(session, codigo="PVD", nombre="Otro", lote_produccion=100)
    await _make_costo(session, otro, harina, cantidad=50)
    fila_solo = await _make_programacion(session, solo, FECHA, plan=100, responsable="Panaderia")
    await _make_programacion(session, otro, FECHA, plan=100, responsable="Pastas")

    ordenes = (await client.post(
        "/costos/ordenes-produccion/generar",
        json={"fecha": FECHA.isoformat(), "cantidades": [{"programacion_id": fila_solo.id, "cantidad": 0}]},
    )).json()

    assert len(ordenes) == 1
    assert ordenes[0]["responsable"] == "Pastas"


async def test_override_for_unknown_programacion_row_is_ignored(client, session):
    harina = await _make_insumo(session)
    producto = await _make_producto(session, codigo="PV5", nombre="Pan5", lote_produccion=100)
    await _make_costo(session, producto, harina, cantidad=50)
    await _make_programacion(session, producto, FECHA, plan=100)

    orden = (await client.post(
        "/costos/ordenes-produccion/generar",
        json={"fecha": FECHA.isoformat(), "cantidades": [{"programacion_id": 999999, "cantidad": 5}]},
    )).json()[0]

    assert orden["productos"][0]["cantidad_planeada"] == 100  # cae de vuelta al plan


async def test_negative_override_is_rejected(client, session):
    producto = await _make_producto(session, codigo="PV6", nombre="Pan6")
    fila = await _make_programacion(session, producto, FECHA, plan=100)

    response = await client.post(
        "/costos/ordenes-produccion/preview",
        json={"fecha": FECHA.isoformat(), "cantidades": [{"programacion_id": fila.id, "cantidad": -1}]},
    )
    assert response.status_code in (400, 422)


# ── Redondeo de insumos ──────────────────────────────────────────────────────

async def test_insumo_quantity_is_rounded_half_up(client, session):
    harina = await _make_insumo(session, nombre="Harina")
    producto = await _make_producto(session, codigo="PV7", nombre="Pan7", lote_produccion=100)
    await _make_costo(session, producto, harina, cantidad=50)
    await _make_programacion(session, producto, FECHA, plan=101)

    orden = (await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})).json()[0]

    # 101/100 * 50 = 50.5 -> half-up -> 51 (round() de Python daría 50)
    assert orden["insumos"][0]["cantidad"] == 51


async def test_small_requirement_is_never_rounded_down_to_zero(client, session):
    """La receta no puede tener fracciones (`Costos.cantidad` es Integer), pero
    el escalado sí las produce: cuando se planifica por debajo del lote, un
    insumo de bajo consumo cae por debajo de 0.5 y redondearía a 0. El piso lo
    deja en 1 para que no desaparezca de la orden (design.md Decision 4)."""
    sal = await _make_insumo(session, nombre="Sal", unidad_medida="KG")
    producto = await _make_producto(session, codigo="PV8", nombre="Pan8", lote_produccion=100)
    await _make_costo(session, producto, sal, cantidad=1)
    await _make_programacion(session, producto, FECHA, plan=30)

    orden = (await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})).json()[0]

    # 30/100 * 1 = 0.3 -> redondea a 0, el piso lo lleva a 1
    assert len(orden["insumos"]) == 1
    assert orden["insumos"][0]["cantidad"] == 1


async def test_insumo_not_required_is_omitted(client, session):
    """Requerimiento exactamente 0 sí se omite: el piso solo aplica a > 0."""
    harina = await _make_insumo(session, nombre="Harina")
    sin_receta = await _make_producto(session, codigo="PV8B", nombre="SinReceta", lote_produccion=100)
    await _make_costo(session, sin_receta, harina, cantidad=0)
    await _make_programacion(session, sin_receta, FECHA, plan=100)

    orden = (await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})).json()[0]

    assert orden["insumos"] == []


async def test_reserva_matches_the_insumo_linea(client, session):
    harina = await _make_insumo(session, nombre="Harina")
    producto = await _make_producto(session, codigo="PV9", nombre="Pan9", lote_produccion=100)
    await _make_costo(session, producto, harina, cantidad=50)
    await _make_programacion(session, producto, FECHA, plan=101)

    orden = (await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})).json()[0]
    assert orden["insumos"][0]["cantidad"] == 51

    movimientos = (await session.execute(
        select(StockMovimiento).where(StockMovimiento.tipo == "RESERVA")
    )).scalars().all()
    assert len(movimientos) == 1
    assert movimientos[0].cantidad == 51
    assert float(movimientos[0].cantidad).is_integer()


async def test_consumo_matches_the_reserva(client, session):
    harina = await _make_insumo(session, nombre="Harina", cantidad=1000)
    producto = await _make_producto(session, codigo="PV10", nombre="Pan10", lote_produccion=100)
    await _make_costo(session, producto, harina, cantidad=50)
    await _make_programacion(session, producto, FECHA, plan=101)

    orden = (await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})).json()[0]
    await client.post(f"/costos/ordenes-produccion/{orden['id']}/iniciar")

    insumo = (await client.get(f"/costos/insumos/{harina.id}")).json()
    assert insumo["cantidad"] == 1000 - 51  # consumió exactamente lo reservado
