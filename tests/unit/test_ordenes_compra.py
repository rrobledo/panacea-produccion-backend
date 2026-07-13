from datetime import date


async def _create_proveedor(client) -> dict:
    response = await client.post("/costos/proveedores", json={"nombre": "Molinos", "cuit": "20-99999999-0"})
    assert response.status_code == 201
    return response.json()


async def test_create_orden_de_compra(client):
    proveedor = await _create_proveedor(client)
    response = await client.post(
        "/costos/ordenes-compra",
        json={
            "proveedor_id": proveedor["id"],
            "fecha": date.today().isoformat(),
            "detalle": [{"descripcion": "Harina 000", "cantidad_pedida": 100}],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["estado"] == "PENDIENTE"
    assert body["detalle"][0]["cantidad_recibida"] == 0
    assert body["proveedor_nombre"] == "Molinos"

    listed = (await client.get("/costos/ordenes-compra")).json()
    assert next(o for o in listed if o["id"] == body["id"])["proveedor_nombre"] == "Molinos"


async def test_partial_reception_sets_estado_parcial(client):
    proveedor = await _create_proveedor(client)
    orden = (
        await client.post(
            "/costos/ordenes-compra",
            json={
                "proveedor_id": proveedor["id"],
                "fecha": date.today().isoformat(),
                "detalle": [{"descripcion": "Harina 000", "cantidad_pedida": 100}],
            },
        )
    ).json()

    await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "F1",
            "fecha": date.today().isoformat(),
            "orden_compra_id": orden["id"],
            "detalle": [{"descripcion": "Harina 000", "cantidad": 40, "precio_unitario": 100}],
        },
    )

    updated = (await client.get(f"/costos/ordenes-compra/{orden['id']}")).json()
    assert updated["estado"] == "PARCIAL"
    assert updated["detalle"][0]["cantidad_recibida"] == 40


async def test_list_ordenes_compra_filters_by_estado(client):
    proveedor = await _create_proveedor(client)
    pendiente = (
        await client.post(
            "/costos/ordenes-compra",
            json={
                "proveedor_id": proveedor["id"],
                "fecha": date.today().isoformat(),
                "detalle": [{"descripcion": "Harina 000", "cantidad_pedida": 100}],
            },
        )
    ).json()
    recibida = (
        await client.post(
            "/costos/ordenes-compra",
            json={
                "proveedor_id": proveedor["id"],
                "fecha": date.today().isoformat(),
                "detalle": [{"descripcion": "Azúcar", "cantidad_pedida": 50}],
            },
        )
    ).json()
    await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "F1",
            "fecha": date.today().isoformat(),
            "orden_compra_id": recibida["id"],
            "detalle": [{"descripcion": "Azúcar", "cantidad": 50, "precio_unitario": 100}],
        },
    )

    unfiltered = (await client.get("/costos/ordenes-compra")).json()
    assert {o["id"] for o in unfiltered} >= {pendiente["id"], recibida["id"]}

    filtered = (await client.get("/costos/ordenes-compra", params={"estado": "RECIBIDA"})).json()
    assert {o["id"] for o in filtered} == {recibida["id"]}


async def test_list_ordenes_compra_filters_by_proveedor(client):
    proveedor_a = await _create_proveedor(client)
    proveedor_b_response = await client.post(
        "/costos/proveedores", json={"nombre": "Aceites SA", "cuit": "20-88888888-0"}
    )
    assert proveedor_b_response.status_code == 201
    proveedor_b = proveedor_b_response.json()

    orden_a = (
        await client.post(
            "/costos/ordenes-compra",
            json={
                "proveedor_id": proveedor_a["id"],
                "fecha": date.today().isoformat(),
                "detalle": [{"descripcion": "Harina 000", "cantidad_pedida": 100}],
            },
        )
    ).json()
    orden_b = (
        await client.post(
            "/costos/ordenes-compra",
            json={
                "proveedor_id": proveedor_b["id"],
                "fecha": date.today().isoformat(),
                "detalle": [{"descripcion": "Aceite", "cantidad_pedida": 50}],
            },
        )
    ).json()

    unfiltered = (await client.get("/costos/ordenes-compra")).json()
    assert {o["id"] for o in unfiltered} >= {orden_a["id"], orden_b["id"]}

    filtered = (
        await client.get("/costos/ordenes-compra", params={"proveedor_id": proveedor_a["id"]})
    ).json()
    assert {o["id"] for o in filtered} == {orden_a["id"]}


async def test_full_reception_sets_estado_recibida(client):
    proveedor = await _create_proveedor(client)
    orden = (
        await client.post(
            "/costos/ordenes-compra",
            json={
                "proveedor_id": proveedor["id"],
                "fecha": date.today().isoformat(),
                "detalle": [{"descripcion": "Harina 000", "cantidad_pedida": 100}],
            },
        )
    ).json()

    await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "F1",
            "fecha": date.today().isoformat(),
            "orden_compra_id": orden["id"],
            "detalle": [{"descripcion": "Harina 000", "cantidad": 60, "precio_unitario": 100}],
        },
    )
    await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "F2",
            "fecha": date.today().isoformat(),
            "orden_compra_id": orden["id"],
            "detalle": [{"descripcion": "Harina 000", "cantidad": 40, "precio_unitario": 100}],
        },
    )

    updated = (await client.get(f"/costos/ordenes-compra/{orden['id']}")).json()
    assert updated["estado"] == "RECIBIDA"
    assert updated["detalle"][0]["cantidad_recibida"] == 100
