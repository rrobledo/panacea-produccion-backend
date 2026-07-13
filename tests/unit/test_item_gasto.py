async def test_list_items_gasto_filters_by_name(client):
    await client.post("/costos/items-gasto", json={"nombre": "Flete"})
    await client.post("/costos/items-gasto", json={"nombre": "Alquiler"})

    response = await client.get("/costos/items-gasto", params={"nombre": "flet"})
    assert response.status_code == 200
    nombres = [i["nombre"] for i in response.json()]
    assert nombres == ["Flete"]


async def test_create_item_gasto_returns_201_with_generated_id(client):
    response = await client.post("/costos/items-gasto", json={"codigo": "FLE", "nombre": "Flete"})
    assert response.status_code == 201
    body = response.json()
    assert body["nombre"] == "Flete"
    assert body["activo"] is True
    assert isinstance(body["id"], int)


async def test_get_item_gasto_not_found(client):
    response = await client.get("/costos/items-gasto/999999")
    assert response.status_code == 404


async def test_update_item_gasto(client):
    created = (await client.post("/costos/items-gasto", json={"nombre": "Flete"})).json()
    response = await client.put(
        f"/costos/items-gasto/{created['id']}", json={"nombre": "Flete y acarreo", "activo": False}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["nombre"] == "Flete y acarreo"
    assert body["activo"] is False


async def test_delete_item_gasto(client):
    created = (await client.post("/costos/items-gasto", json={"nombre": "Flete"})).json()
    response = await client.delete(f"/costos/items-gasto/{created['id']}")
    assert response.status_code == 204
    assert (await client.get(f"/costos/items-gasto/{created['id']}")).status_code == 404
