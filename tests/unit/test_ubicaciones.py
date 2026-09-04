async def test_create_and_list_ubicaciones(client):
    await client.post("/costos/ubicaciones", json={"nombre": "Depósito Central - Estante 3"})
    await client.post("/costos/ubicaciones", json={"nombre": "Cámara - Sector 1"})

    response = await client.get("/costos/ubicaciones")
    assert response.status_code == 200
    nombres = sorted(u["nombre"] for u in response.json())
    assert nombres == ["Cámara - Sector 1", "Depósito Central - Estante 3"]


async def test_list_ubicaciones_filters_by_nombre(client):
    # EntityPicker (frontend) searches via ?nombre=, not ?q= — see
    # src/components/form/EntityPicker.jsx's default searchField.
    await client.post("/costos/ubicaciones", json={"nombre": "Depósito Central"})
    await client.post("/costos/ubicaciones", json={"nombre": "Cámara - Sector 1"})

    response = await client.get("/costos/ubicaciones", params={"nombre": "cámara"})
    assert response.status_code == 200
    nombres = [u["nombre"] for u in response.json()]
    assert nombres == ["Cámara - Sector 1"]


async def test_update_ubicacion(client):
    created = await client.post("/costos/ubicaciones", json={"nombre": "Original"})
    ubicacion_id = created.json()["id"]

    response = await client.put(f"/costos/ubicaciones/{ubicacion_id}", json={"nombre": "Renombrada"})
    assert response.status_code == 200
    assert response.json()["nombre"] == "Renombrada"


async def test_delete_ubicacion_without_references_succeeds(client):
    created = await client.post("/costos/ubicaciones", json={"nombre": "Sin uso"})
    ubicacion_id = created.json()["id"]

    response = await client.delete(f"/costos/ubicaciones/{ubicacion_id}")
    assert response.status_code == 204

    response = await client.get(f"/costos/ubicaciones/{ubicacion_id}")
    assert response.status_code == 404


async def test_delete_ubicacion_referenced_by_producto_fabricado_is_blocked(client, session):
    from datetime import date, datetime, timezone

    from app.models.ordenes_produccion import OrdenProduccion, OrdenProduccionProductoLinea, ProductoFabricado
    from app.models.productos import Productos
    from app.models.ubicacion import Ubicacion

    producto = Productos(
        codigo="P1", nombre="Medialuna", utilidad=30, precio_actual=100, lote_produccion=100, is_producto=True
    )
    ubicacion = Ubicacion(nombre="Depósito Central")
    session.add_all([producto, ubicacion])
    await session.commit()
    await session.refresh(producto)
    await session.refresh(ubicacion)

    orden = OrdenProduccion(
        codigo="TEST-01", fecha_fabricacion=date.today(), responsable="Todos", estado="FINALIZADA",
        fecha_creacion=datetime.now(timezone.utc),
    )
    session.add(orden)
    await session.flush()
    session.add(OrdenProduccionProductoLinea(orden_id=orden.id, producto_id=producto.id, cantidad_planeada=100))
    session.add(
        ProductoFabricado(
            orden_id=orden.id, producto_id=producto.id, cantidad_fabricada=100, ubicacion_id=ubicacion.id,
            fecha=datetime.now(timezone.utc),
        )
    )
    await session.commit()

    response = await client.delete(f"/costos/ubicaciones/{ubicacion.id}")
    assert response.status_code == 422
