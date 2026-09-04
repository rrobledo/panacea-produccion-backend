from datetime import date

from app.models.insumos import Insumos
from app.models.productos import Costos, Productos
from app.models.programacion import Programacion

FECHA = date(2026, 8, 25)


async def _producto(session, **overrides):
    defaults = dict(
        codigo="PF1", categoria="PANADERIA", nombre="Producto", utilidad=30, precio_actual=1000,
        unidad_medida="UN", lote_produccion=100, tiempo_produccion=2, responsable="Todos",
        is_producto=True, habilitado=True, prioridad=10,
    )
    defaults.update(overrides)
    p = Productos(**defaults)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


async def _crear_orden_finalizada(client, session, producto, ubicacion_id, cantidad, responsable):
    """Genera, inicia y finaliza una orden para `producto` en su propia fecha."""
    harina = Insumos(nombre=f"Harina {producto.codigo}", unidad_medida="KG", cantidad=100000, precio=10)
    session.add(harina)
    await session.commit()
    await session.refresh(harina)
    session.add(Costos(producto_id=producto.id, insumo_id=harina.id, cantidad=10))
    session.add(Programacion(fecha=FECHA, producto_id=producto.id, producto_nombre=producto.nombre,
                             responsable=responsable, plan=cantidad, prod=None))
    await session.commit()

    generar = await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})
    assert generar.status_code == 201
    orden = next(o for o in generar.json() if o["responsable"] == responsable)
    await client.post(f"/costos/ordenes-produccion/{orden['id']}/iniciar")
    await client.post(
        f"/costos/ordenes-produccion/{orden['id']}/finalizar",
        json={"lineas": [{"producto_id": producto.id, "cantidad_fabricada": cantidad,
                          "ubicacion_id": ubicacion_id}]},
    )
    return orden


async def test_filtra_productos_fabricados_por_orden(client, session):
    ubicacion = (await client.post("/costos/ubicaciones", json={"nombre": "Depósito"})).json()

    pan = await _producto(session, codigo="PFA", nombre="Pan")
    torta = await _producto(session, codigo="PFB", nombre="Torta")

    # Ambas órdenes se generan de una sola vez (misma fecha, distinto responsable)
    harina = Insumos(nombre="Harina común", unidad_medida="KG", cantidad=100000, precio=10)
    session.add(harina)
    await session.commit()
    await session.refresh(harina)
    session.add(Costos(producto_id=pan.id, insumo_id=harina.id, cantidad=10))
    session.add(Costos(producto_id=torta.id, insumo_id=harina.id, cantidad=10))
    session.add(Programacion(fecha=FECHA, producto_id=pan.id, producto_nombre=pan.nombre,
                             responsable="Panaderia", plan=100, prod=None))
    session.add(Programacion(fecha=FECHA, producto_id=torta.id, producto_nombre=torta.nombre,
                             responsable="Pasteleria", plan=50, prod=None))
    await session.commit()

    ordenes = (await client.post("/costos/ordenes-produccion/generar", json={"fecha": FECHA.isoformat()})).json()
    assert len(ordenes) == 2
    orden_pan = next(o for o in ordenes if o["responsable"] == "Panaderia")
    orden_torta = next(o for o in ordenes if o["responsable"] == "Pasteleria")

    for orden, producto, cant in [(orden_pan, pan, 100), (orden_torta, torta, 50)]:
        await client.post(f"/costos/ordenes-produccion/{orden['id']}/iniciar")
        await client.post(
            f"/costos/ordenes-produccion/{orden['id']}/finalizar",
            json={"lineas": [{"producto_id": producto.id, "cantidad_fabricada": cant,
                              "ubicacion_id": ubicacion["id"]}]},
        )

    solo_pan = await client.get("/costos/productos_fabricados", params={"orden_id": orden_pan["id"]})
    assert solo_pan.status_code == 200
    rows = solo_pan.json()
    assert len(rows) == 1
    assert rows[0]["orden_id"] == orden_pan["id"]
    assert rows[0]["producto"]["nombre"] == "Pan"

    solo_torta = await client.get("/costos/productos_fabricados", params={"orden_id": orden_torta["id"]})
    assert [r["producto"]["nombre"] for r in solo_torta.json()] == ["Torta"]


async def test_sin_orden_id_devuelve_todos(client, session):
    ubicacion = (await client.post("/costos/ubicaciones", json={"nombre": "Depósito"})).json()
    pan = await _producto(session, codigo="PFC", nombre="Pan2")
    await _crear_orden_finalizada(client, session, pan, ubicacion["id"], 100, "Panaderia")

    todos = await client.get("/costos/productos_fabricados")
    assert todos.status_code == 200
    assert len(todos.json()) == 1


async def test_orden_id_inexistente_devuelve_vacio(client, session):
    respuesta = await client.get("/costos/productos_fabricados", params={"orden_id": 999999})
    assert respuesta.status_code == 200
    assert respuesta.json() == []
