async def _create_empresa(client, headers, nombre="Acme SA") -> dict:
    response = await client.post("/crm/empresas", json={"nombre": nombre}, headers=headers)
    assert response.status_code == 201
    return response.json()


async def _create_rubro(client, headers, nombre="Panaderia") -> dict:
    response = await client.post("/crm/catalogos/rubros", json={"nombre": nombre}, headers=headers)
    assert response.status_code == 201
    return response.json()


async def _create_ciudad(client, headers, nombre="Cordoba") -> dict:
    response = await client.post("/crm/catalogos/ciudades", json={"nombre": nombre}, headers=headers)
    assert response.status_code == 201
    return response.json()


async def test_create_contacto_b2c_sin_erp(client, auth_header):
    headers = await auth_header("vendedor")
    response = await client.post(
        "/crm/contactos", json={"tipo": "B2C", "nombre": "Juan Perez"}, headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["erp_cliente_id"] is None
    assert body["tipo"] == "B2C"


async def test_create_contacto_b2b_con_empresa(client, auth_header):
    headers = await auth_header("vendedor")
    empresa = await _create_empresa(client, headers)
    response = await client.post(
        "/crm/contactos",
        json={"tipo": "B2B", "nombre": "Maria Lopez", "empresa_id": empresa["id"]},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["empresa_id"] == empresa["id"]
    assert body["empresa_nombre"] == empresa["nombre"]


async def test_create_contacto_con_erp_cliente_inexistente_es_rechazado(client, auth_header):
    headers = await auth_header("vendedor")
    response = await client.post(
        "/crm/contactos", json={"tipo": "B2C", "nombre": "Juan Perez", "erp_cliente_id": 999999}, headers=headers
    )
    assert response.status_code == 400


async def test_create_contacto_con_rubro_inexistente_es_rechazado(client, auth_header):
    headers = await auth_header("vendedor")
    response = await client.post(
        "/crm/contactos", json={"tipo": "B2C", "nombre": "Juan Perez", "rubro_id": 999999}, headers=headers
    )
    assert response.status_code == 400


async def test_create_contacto_con_catalogos_existentes(client, auth_header):
    headers = await auth_header("vendedor")
    rubro = await _create_rubro(client, headers)
    ciudad = await _create_ciudad(client, headers)
    response = await client.post(
        "/crm/contactos",
        json={"tipo": "B2C", "nombre": "Juan Perez", "rubro_id": rubro["id"], "ciudad_id": ciudad["id"]},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["rubro_nombre"] == rubro["nombre"]
    assert body["ciudad_nombre"] == ciudad["nombre"]


async def test_list_contactos_de_una_empresa(client, auth_header):
    headers = await auth_header("vendedor")
    empresa = await _create_empresa(client, headers)
    otra_empresa = await _create_empresa(client, headers, nombre="Otra SA")
    await client.post(
        "/crm/contactos", json={"tipo": "B2B", "nombre": "A", "empresa_id": empresa["id"]}, headers=headers
    )
    await client.post(
        "/crm/contactos", json={"tipo": "B2B", "nombre": "B", "empresa_id": empresa["id"]}, headers=headers
    )
    await client.post(
        "/crm/contactos", json={"tipo": "B2B", "nombre": "C", "empresa_id": otra_empresa["id"]}, headers=headers
    )

    response = await client.get("/crm/contactos", params={"empresa_id": empresa["id"]}, headers=headers)
    assert response.status_code == 200
    nombres = {c["nombre"] for c in response.json()}
    assert nombres == {"A", "B"}


async def test_update_contacto_writes_auditoria(client, auth_header, session):
    from sqlalchemy import select

    from app.models.crm_auditoria import CrmAuditoria

    headers = await auth_header("vendedor")
    created = await client.post("/crm/contactos", json={"tipo": "B2C", "nombre": "Juan"}, headers=headers)
    contacto_id = created.json()["id"]

    response = await client.put(
        f"/crm/contactos/{contacto_id}", json={"tipo": "B2C", "nombre": "Juan Actualizado"}, headers=headers
    )
    assert response.status_code == 200

    result = await session.execute(
        select(CrmAuditoria).where(CrmAuditoria.entidad == "Contacto", CrmAuditoria.campo == "nombre")
    )
    entry = result.scalar_one()
    assert entry.valor_anterior == "Juan"
    assert entry.valor_nuevo == "Juan Actualizado"


async def test_crm_endpoints_require_authentication(client):
    response = await client.get("/crm/contactos")
    assert response.status_code == 401


async def test_crm_endpoints_allow_any_authenticated_role(client, auth_header):
    # require_role(*CRM_ROLES) was replaced by require_authenticated(): any
    # valid session is accepted now, not just the commercial roles.
    headers = await auth_header("user")
    response = await client.get("/crm/contactos", headers=headers)
    assert response.status_code == 200


async def test_create_and_list_vendedor(client, auth_header):
    headers = await auth_header("supervisor_comercial")
    response = await client.post("/crm/vendedores", json={"nombre": "Carlos Vendedor"}, headers=headers)
    assert response.status_code == 201

    listed = await client.get("/crm/vendedores", headers=headers)
    assert any(v["nombre"] == "Carlos Vendedor" for v in listed.json())
