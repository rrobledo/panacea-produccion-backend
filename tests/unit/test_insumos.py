async def test_list_insumos_filters_by_name(client):
    await client.post("/costos/insumos", json={"nombre": "Harina 000", "unidad_medida": "KG", "cantidad": 1, "precio": 1000})
    await client.post("/costos/insumos", json={"nombre": "Azucar", "unidad_medida": "KG", "cantidad": 1, "precio": 800})

    response = await client.get("/costos/insumos", params={"nombre": "harina"})
    assert response.status_code == 200
    nombres = [i["nombre"] for i in response.json()]
    assert nombres == ["Harina 000"]


async def test_list_insumos_q_alias_filters_like_nombre(client):
    await client.post("/costos/insumos", json={"nombre": "Harina 000", "unidad_medida": "KG", "cantidad": 1, "precio": 1000})
    await client.post("/costos/insumos", json={"nombre": "Azucar", "unidad_medida": "KG", "cantidad": 1, "precio": 800})

    response = await client.get("/costos/insumos", params={"q": "harina"})
    assert response.status_code == 200
    nombres = [i["nombre"] for i in response.json()]
    assert nombres == ["Harina 000"]


async def test_create_insumo_returns_201_with_generated_id(client):
    response = await client.post(
        "/costos/insumos", json={"nombre": "Levadura", "unidad_medida": "GR", "cantidad": 500, "precio": 200}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["nombre"] == "Levadura"
    assert isinstance(body["id"], int)
