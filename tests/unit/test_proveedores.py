async def test_create_proveedor_with_new_fields_and_defaults(client):
    payload = {
        "codigo": "PROV-001",
        "nombre": "Acindar",
        "nombre_fantasia": "Acindar SA",
        "cuit": "20-11111111-1",
        "condicion_iva": "RESPONSABLE_INSCRIPTO",
        "direccion": "Av. Siempreviva 742",
    }
    response = await client.post("/costos/proveedores", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["codigo"] == "PROV-001"
    assert body["nombre_fantasia"] == "Acindar SA"
    assert body["condicion_iva"] == "RESPONSABLE_INSCRIPTO"
    # condicion_pago defaults to CUENTA_CORRIENTE when not provided.
    assert body["condicion_pago"] == "CUENTA_CORRIENTE"
    assert body["estado"] == "activo"


async def test_create_proveedor_without_condicion_iva_leaves_it_null(client):
    response = await client.post(
        "/costos/proveedores", json={"nombre": "Sin Datos Fiscales", "cuit": "20-22222222-2"}
    )
    assert response.status_code == 201
    assert response.json()["condicion_iva"] is None


async def test_reject_unknown_condicion_iva(client):
    response = await client.post(
        "/costos/proveedores",
        json={"nombre": "Malo", "cuit": "20-33333333-3", "condicion_iva": "NO_EXISTE"},
    )
    assert response.status_code == 400


async def test_create_proveedor_with_explicit_condicion_pago_contado(client):
    response = await client.post(
        "/costos/proveedores",
        json={"nombre": "Contado SA", "cuit": "20-44444444-4", "condicion_pago": "CONTADO"},
    )
    assert response.status_code == 201
    assert response.json()["condicion_pago"] == "CONTADO"


async def test_list_proveedores_q_alias_filters_like_nombre(client):
    await client.post("/costos/proveedores", json={"nombre": "Acindar", "cuit": "20-11111111-1"})
    await client.post("/costos/proveedores", json={"nombre": "Ternium", "cuit": "20-22222222-2"})

    response = await client.get("/costos/proveedores", params={"q": "acin"})
    assert response.status_code == 200
    nombres = [p["nombre"] for p in response.json()]
    assert nombres == ["Acindar"]


async def test_list_proveedores_limit_caps_results(client):
    await client.post("/costos/proveedores", json={"nombre": "Acindar", "cuit": "20-11111111-1"})
    await client.post("/costos/proveedores", json={"nombre": "Ternium", "cuit": "20-22222222-2"})

    response = await client.get("/costos/proveedores", params={"limit": 1})
    assert response.status_code == 200
    assert len(response.json()) == 1
