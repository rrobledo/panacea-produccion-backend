async def _create_insumo(client, cantidad=100):
    response = await client.post(
        "/costos/insumos", json={"nombre": "Harina 000", "unidad_medida": "KG", "cantidad": cantidad, "precio": 1000}
    )
    return response.json()


async def test_create_insumo_seeds_opening_ajuste_movement(client):
    insumo = await _create_insumo(client, cantidad=250)

    response = await client.get(f"/costos/insumos/{insumo['id']}/movimientos")
    assert response.status_code == 200
    movimientos = response.json()
    assert len(movimientos) == 1
    assert movimientos[0]["tipo"] == "AJUSTE"
    assert movimientos[0]["cantidad"] == 250
    assert movimientos[0]["referencia"] == "Apertura"


async def test_create_insumo_with_zero_cantidad_seeds_no_movement(client):
    insumo = await _create_insumo(client, cantidad=0)

    response = await client.get(f"/costos/insumos/{insumo['id']}/movimientos")
    assert response.json() == []


async def test_put_insumo_no_longer_accepts_cantidad(client):
    insumo = await _create_insumo(client, cantidad=100)

    response = await client.put(
        f"/costos/insumos/{insumo['id']}",
        json={"nombre": "Harina 0000", "unidad_medida": "KG", "precio": 1200, "cantidad": 999},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["nombre"] == "Harina 0000"
    assert body["cantidad"] == 100  # unchanged — cantidad in the payload is ignored


async def test_ajustar_stock_creates_movement_and_updates_cantidad(client):
    insumo = await _create_insumo(client, cantidad=100)

    response = await client.post(
        f"/costos/insumos/{insumo['id']}/movimientos", json={"cantidad": -20, "motivo": "Merma por rotura"}
    )
    assert response.status_code == 201
    assert response.json()["tipo"] == "AJUSTE"
    assert response.json()["cantidad"] == -20

    get_response = await client.get(f"/costos/insumos/{insumo['id']}")
    assert get_response.json()["cantidad"] == 80

    history = await client.get(f"/costos/insumos/{insumo['id']}/movimientos")
    tipos = [m["tipo"] for m in history.json()]
    assert tipos == ["AJUSTE", "AJUSTE"]  # most recent first: the manual ajuste, then apertura


async def test_insumo_comprometido_and_disponible_reflect_open_reservas(client, session):
    from datetime import date, datetime, timezone

    from app.models.ordenes_produccion import OrdenProduccion, OrdenProduccionInsumoLinea

    insumo = await _create_insumo(client, cantidad=100)

    orden = OrdenProduccion(
        codigo="TEST-01", fecha_fabricacion=date.today(), responsable="Todos", estado="ASIGNADA",
        fecha_creacion=datetime.now(timezone.utc),
    )
    session.add(orden)
    await session.flush()
    session.add(OrdenProduccionInsumoLinea(orden_id=orden.id, insumo_id=insumo["id"], cantidad=30))
    await session.commit()

    response = await client.get(f"/costos/insumos/{insumo['id']}")
    body = response.json()
    assert body["cantidad"] == 100
    assert body["comprometido"] == 30
    assert body["disponible"] == 70
