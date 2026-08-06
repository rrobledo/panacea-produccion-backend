from datetime import date

from sqlalchemy import select

from app.models.crm_auditoria import CrmAuditoria


async def _create_contacto(client, headers) -> dict:
    response = await client.post("/crm/contactos", json={"tipo": "B2B", "nombre": "Juan"}, headers=headers)
    return response.json()


async def _create_vendedor(client, headers) -> dict:
    response = await client.post("/crm/vendedores", json={"nombre": "Carlos"}, headers=headers)
    return response.json()


async def test_create_visita(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)
    vendedor = await _create_vendedor(client, headers)

    response = await client.post(
        "/crm/visitas",
        json={"contacto_id": contacto["id"], "vendedor_id": vendedor["id"], "fecha": date.today().isoformat()},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["contacto_id"] == contacto["id"]


async def test_create_visita_contacto_inexistente_es_rechazado(client, auth_header):
    headers = await auth_header("vendedor")
    vendedor = await _create_vendedor(client, headers)

    response = await client.post(
        "/crm/visitas",
        json={"contacto_id": 999999, "vendedor_id": vendedor["id"], "fecha": date.today().isoformat()},
        headers=headers,
    )
    assert response.status_code == 400


async def test_create_visita_vendedor_inexistente_es_rechazado(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)

    response = await client.post(
        "/crm/visitas",
        json={"contacto_id": contacto["id"], "vendedor_id": 999999, "fecha": date.today().isoformat()},
        headers=headers,
    )
    assert response.status_code == 400


async def test_create_visita_queda_auditada(client, auth_header, session):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)
    vendedor = await _create_vendedor(client, headers)

    await client.post(
        "/crm/visitas",
        json={"contacto_id": contacto["id"], "vendedor_id": vendedor["id"], "fecha": date.today().isoformat()},
        headers=headers,
    )

    result = await session.execute(select(CrmAuditoria).where(CrmAuditoria.entidad == "Visita"))
    assert result.scalar_one() is not None
