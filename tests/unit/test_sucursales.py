async def test_create_sucursal(client):
    resp = await client.post("/costos/sucursales", json={"nombre": "Sucursal Centro", "tipo": "SUCURSAL"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["nombre"] == "Sucursal Centro"
    assert body["tipo"] == "SUCURSAL"
    assert body["activa"] is True


async def test_create_fabrica(client):
    resp = await client.post("/costos/sucursales", json={"nombre": "Fábrica", "tipo": "FABRICA"})
    assert resp.status_code == 201
    assert resp.json()["tipo"] == "FABRICA"


async def test_create_sucursal_invalid_tipo_is_rejected(client):
    resp = await client.post("/costos/sucursales", json={"nombre": "X", "tipo": "DEPOSITO"})
    assert resp.status_code == 400


async def test_filter_by_tipo_and_activa(client):
    await client.post("/costos/sucursales", json={"nombre": "Centro", "tipo": "SUCURSAL"})
    await client.post("/costos/sucursales", json={"nombre": "Fábrica", "tipo": "FABRICA"})
    inactiva = await client.post("/costos/sucursales", json={"nombre": "Norte", "tipo": "SUCURSAL"})
    await client.put(f"/costos/sucursales/{inactiva.json()['id']}", json={"activa": False})

    resp = await client.get("/costos/sucursales", params={"tipo": "SUCURSAL", "activa": True})
    assert resp.status_code == 200
    nombres = {s["nombre"] for s in resp.json()}
    assert nombres == {"Centro"}


async def test_desactivar_sucursal_no_borra_datos(client):
    creada = await client.post("/costos/sucursales", json={"nombre": "Norte", "tipo": "SUCURSAL"})
    sucursal_id = creada.json()["id"]

    resp = await client.put(f"/costos/sucursales/{sucursal_id}", json={"activa": False})
    assert resp.status_code == 200
    assert resp.json()["activa"] is False

    listado = await client.get("/costos/sucursales")
    assert any(s["id"] == sucursal_id for s in listado.json())
