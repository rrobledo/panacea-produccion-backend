from datetime import date

from app.models.insumos import Insumos
from app.models.productos import Costos, Productos
from app.models.programacion import Programacion


async def _make_producto(session, **overrides):
    defaults = dict(
        codigo="P1",
        categoria="PANADERIA",
        nombre="Producto",
        utilidad=30,
        precio_actual=1000,
        unidad_medida="UN",
        lote_produccion=100,
        tiempo_produccion=2,
        responsable="Todos",
        is_producto=True,
        habilitado=True,
        prioridad=10,
    )
    defaults.update(overrides)
    producto = Productos(**defaults)
    session.add(producto)
    await session.commit()
    await session.refresh(producto)
    return producto


async def _make_insumo(session, **overrides):
    defaults = dict(nombre="Harina", unidad_medida="KG", cantidad=1000, precio=1000)
    defaults.update(overrides)
    insumo = Insumos(**defaults)
    session.add(insumo)
    await session.commit()
    await session.refresh(insumo)
    return insumo


async def _make_costo(session, producto, insumo, cantidad):
    costo = Costos(producto_id=producto.id, insumo_id=insumo.id, cantidad=cantidad)
    session.add(costo)
    await session.commit()


async def _make_programacion(session, producto, fecha, plan, responsable="Todos"):
    row = Programacion(fecha=fecha, producto_id=producto.id, producto_nombre=producto.nombre, responsable=responsable, plan=plan, prod=None)
    session.add(row)
    await session.commit()


FECHA = date(2026, 8, 25)


async def test_generar_ordenes_groups_shared_producto_base_into_single_orden(client, session):
    harina = await _make_insumo(session, nombre="Harina", cantidad=10000)

    masa = await _make_producto(session, codigo="M1", nombre="Masa", is_producto=False, lote_produccion=100)
    await _make_costo(session, masa, harina, cantidad=50)  # 50kg harina por lote de 100

    medialuna = await _make_producto(
        session, codigo="F1", nombre="Medialuna", is_producto=True, lote_produccion=100, producto_base_id=masa.id
    )
    factura = await _make_producto(
        session, codigo="F2", nombre="Factura", is_producto=True, lote_produccion=100, producto_base_id=masa.id
    )

    await _make_programacion(session, medialuna, FECHA, plan=100, responsable="Pasteleria")
    await _make_programacion(session, factura, FECHA, plan=200, responsable="Pasteleria")

    response = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    assert response.status_code == 201
    ordenes = response.json()
    assert len(ordenes) == 1
    orden = ordenes[0]
    assert orden["estado"] == "ASIGNADA"
    assert orden["responsable"] == "Pasteleria"
    assert {p["producto_id"] for p in orden["productos"]} == {medialuna.id, factura.id}

    # cantidad_total = 100 + 200 = 300, scale = 300/100 = 3, insumo = 50*3 = 150
    assert len(orden["insumos"]) == 1
    assert orden["insumos"][0]["insumo_id"] == harina.id
    assert orden["insumos"][0]["cantidad"] == 150


async def test_generar_ordenes_separates_by_responsable_even_with_same_base(client, session):
    harina = await _make_insumo(session, nombre="Harina", cantidad=10000)
    masa = await _make_producto(session, codigo="M2", nombre="Masa", is_producto=False, lote_produccion=100)
    await _make_costo(session, masa, harina, cantidad=10)

    p1 = await _make_producto(session, codigo="F3", nombre="P1", producto_base_id=masa.id, lote_produccion=100)
    p2 = await _make_producto(session, codigo="F4", nombre="P2", producto_base_id=masa.id, lote_produccion=100)

    await _make_programacion(session, p1, FECHA, plan=50, responsable="Pasteleria")
    await _make_programacion(session, p2, FECHA, plan=50, responsable="Pastas")

    response = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    ordenes = response.json()
    assert len(ordenes) == 2
    responsables = sorted(o["responsable"] for o in ordenes)
    assert responsables == ["Pastas", "Pasteleria"]


async def test_generar_ordenes_twice_same_date_is_rejected(client, session):
    producto = await _make_producto(session, codigo="P9", nombre="Solo", lote_produccion=100)
    await _make_programacion(session, producto, FECHA, plan=10)

    first = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    assert first.status_code == 201

    second = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    assert second.status_code == 422


async def test_full_lifecycle_iniciar_and_finalizar(client, session):
    harina = await _make_insumo(session, nombre="Harina", cantidad=1000)
    producto = await _make_producto(session, codigo="P10", nombre="Pan", lote_produccion=100)
    await _make_costo(session, producto, harina, cantidad=50)
    await _make_programacion(session, producto, FECHA, plan=100, responsable="Panaderia")

    generar = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    orden_id = generar.json()[0]["id"]
    # scale = 100/100 = 1, insumo = 50*1 = 50
    assert generar.json()[0]["insumos"][0]["cantidad"] == 50

    iniciar = await client.post(f"/costos/ordenes-produccion/{orden_id}/iniciar")
    assert iniciar.status_code == 200
    assert iniciar.json()["estado"] == "EN_PRODUCCION"

    insumo_after = await client.get(f"/costos/insumos/{harina.id}")
    assert insumo_after.json()["cantidad"] == 950  # 1000 - 50 consumido

    ubicacion = await client.post("/costos/ubicaciones", json={"nombre": "Depósito Central"})
    ubicacion_desperdicio = await client.post("/costos/ubicaciones", json={"nombre": "Compost"})

    finalizar = await client.post(
        f"/costos/ordenes-produccion/{orden_id}/finalizar",
        json={
            "lineas": [
                {
                    "producto_id": producto.id,
                    "cantidad_fabricada": 95,
                    "ubicacion_id": ubicacion.json()["id"],
                    "cantidad_desperdicio": 5,
                    "ubicacion_desperdicio_id": ubicacion_desperdicio.json()["id"],
                    "motivo_desperdicio": "Se quemó una tanda",
                }
            ]
        },
    )
    assert finalizar.status_code == 200
    assert finalizar.json()["estado"] == "FINALIZADA"

    fabricados = await client.get("/costos/productos_fabricados")
    assert fabricados.status_code == 200
    rows = fabricados.json()
    assert len(rows) == 1
    assert rows[0]["cantidad_fabricada"] == 95
    assert rows[0]["cantidad_desperdicio"] == 5
    assert rows[0]["orden_codigo"] == generar.json()[0]["codigo"]


async def test_finalizar_requires_motivo_and_ubicacion_when_desperdicio_positive(client, session):
    producto = await _make_producto(session, codigo="P11", nombre="Pan2", lote_produccion=100)
    await _make_programacion(session, producto, FECHA, plan=10, responsable="Panaderia")

    generar = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    orden_id = generar.json()[0]["id"]
    await client.post(f"/costos/ordenes-produccion/{orden_id}/iniciar")

    ubicacion = await client.post("/costos/ubicaciones", json={"nombre": "Depósito"})

    response = await client.post(
        f"/costos/ordenes-produccion/{orden_id}/finalizar",
        json={
            "lineas": [
                {
                    "producto_id": producto.id,
                    "cantidad_fabricada": 8,
                    "ubicacion_id": ubicacion.json()["id"],
                    "cantidad_desperdicio": 2,
                }
            ]
        },
    )
    assert response.status_code == 400  # pydantic validation error (see main.py validation_exception_handler)


async def test_iniciar_blocks_when_insufficient_physical_stock(client, session):
    harina = await _make_insumo(session, nombre="Harina", cantidad=10)
    producto = await _make_producto(session, codigo="P12", nombre="Pan3", lote_produccion=100)
    await _make_costo(session, producto, harina, cantidad=50)
    await _make_programacion(session, producto, FECHA, plan=100, responsable="Panaderia")

    generar = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    orden_id = generar.json()[0]["id"]

    response = await client.post(f"/costos/ordenes-produccion/{orden_id}/iniciar")
    assert response.status_code == 422
    assert "insuficiente" in response.json()["detail"].lower()


async def test_cancelar_releases_reserva_for_new_orden(client, session):
    harina = await _make_insumo(session, nombre="Harina", cantidad=1000)
    producto = await _make_producto(session, codigo="P13", nombre="Pan4", lote_produccion=100)
    await _make_costo(session, producto, harina, cantidad=50)
    await _make_programacion(session, producto, FECHA, plan=100, responsable="Panaderia")

    generar = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    orden_id = generar.json()[0]["id"]

    insumo_before = await client.get(f"/costos/insumos/{harina.id}")
    assert insumo_before.json()["comprometido"] == 50

    cancelar = await client.post(f"/costos/ordenes-produccion/{orden_id}/cancelar")
    assert cancelar.status_code == 200
    assert cancelar.json()["estado"] == "CANCELADA"

    insumo_after = await client.get(f"/costos/insumos/{harina.id}")
    assert insumo_after.json()["comprometido"] == 0
    assert insumo_after.json()["cantidad"] == 1000  # nunca se consumió físicamente


async def test_cancelar_only_allowed_from_asignada(client, session):
    producto = await _make_producto(session, codigo="P14", nombre="Pan5", lote_produccion=100)
    await _make_programacion(session, producto, FECHA, plan=10, responsable="Panaderia")

    generar = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    orden_id = generar.json()[0]["id"]
    await client.post(f"/costos/ordenes-produccion/{orden_id}/iniciar")

    response = await client.post(f"/costos/ordenes-produccion/{orden_id}/cancelar")
    assert response.status_code == 422
