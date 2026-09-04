def _payload(**overrides):
    base = dict(
        codigo="P1",
        categoria="PANADERIA",
        nombre="Medialuna",
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
    base.update(overrides)
    return base


async def test_create_producto_with_intermedio_base_succeeds(client):
    masa = await client.post("/costos/productos", json=_payload(codigo="M1", nombre="Masa de Hojaldre", is_producto=False))
    masa_id = masa.json()["id"]

    response = await client.post(
        "/costos/productos", json=_payload(codigo="P1", nombre="Medialuna", producto_base_id=masa_id)
    )
    assert response.status_code == 201
    body = response.json()
    assert body["producto_base_id"] == masa_id
    assert body["producto_base"]["id"] == masa_id
    assert body["producto_base"]["nombre"] == "Masa de Hojaldre"


async def test_create_producto_base_must_not_be_is_producto(client):
    otro_final = await client.post("/costos/productos", json=_payload(codigo="F1", nombre="Factura", is_producto=True))
    otro_final_id = otro_final.json()["id"]

    response = await client.post(
        "/costos/productos", json=_payload(codigo="P2", nombre="Medialuna 2", producto_base_id=otro_final_id)
    )
    assert response.status_code == 422


async def test_producto_cannot_reference_itself_as_base(client):
    created = await client.post("/costos/productos", json=_payload(codigo="P3", nombre="Medialuna 3"))
    producto_id = created.json()["id"]

    response = await client.put(
        f"/costos/productos/{producto_id}", json=_payload(codigo="P3", nombre="Medialuna 3", producto_base_id=producto_id)
    )
    assert response.status_code == 422


async def test_producto_base_cycle_is_rejected(client):
    masa = await client.post("/costos/productos", json=_payload(codigo="M2", nombre="Masa", is_producto=False))
    masa_id = masa.json()["id"]

    intermedio = await client.post(
        "/costos/productos",
        json=_payload(codigo="I1", nombre="Intermedio", is_producto=False, producto_base_id=masa_id),
    )
    intermedio_id = intermedio.json()["id"]

    # masa -> intermedio would close the cycle masa -> intermedio -> masa
    response = await client.put(
        f"/costos/productos/{masa_id}",
        json=_payload(codigo="M2", nombre="Masa", is_producto=False, producto_base_id=intermedio_id),
    )
    assert response.status_code == 422


async def test_list_productos_filters_by_is_producto(client):
    await client.post("/costos/productos", json=_payload(codigo="F2", nombre="Factura Final", is_producto=True))
    await client.post("/costos/productos", json=_payload(codigo="M3", nombre="Masa Intermedia", is_producto=False))

    response = await client.get("/costos/productos", params={"is_producto": False})
    nombres = [p["nombre"] for p in response.json()]
    assert nombres == ["Masa Intermedia"]
