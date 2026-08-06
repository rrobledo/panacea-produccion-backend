from datetime import date

from sqlalchemy import select, text

from app.models.clientes import Clientes
from app.models.crm_auditoria import CrmAuditoria


async def _create_contacto(client, headers, **overrides) -> dict:
    payload = {"tipo": "B2B", "nombre": "Juan"}
    payload.update(overrides)
    response = await client.post("/crm/contactos", json=payload, headers=headers)
    return response.json()


async def _create_vendedor(client, headers) -> dict:
    response = await client.post("/crm/vendedores", json={"nombre": "Carlos"}, headers=headers)
    return response.json()


async def _create_visita(client, headers, contacto_id: int, vendedor_id: int) -> dict:
    response = await client.post(
        "/crm/visitas",
        json={"contacto_id": contacto_id, "vendedor_id": vendedor_id, "fecha": date.today().isoformat()},
        headers=headers,
    )
    return response.json()


async def test_create_oportunidad_etapa_lead_por_defecto(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)

    response = await client.post("/crm/oportunidades", json={"contacto_id": contacto["id"]}, headers=headers)
    assert response.status_code == 201
    assert response.json()["etapa_nombre"] == "Lead"


async def test_cambio_de_etapa(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)
    oportunidad = (
        await client.post("/crm/oportunidades", json={"contacto_id": contacto["id"]}, headers=headers)
    ).json()

    response = await client.put(
        f"/crm/oportunidades/{oportunidad['id']}/etapa", json={"etapa_nombre": "Visita"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["etapa_nombre"] == "Visita"


async def test_crear_oportunidad_desde_visita(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)
    vendedor = await _create_vendedor(client, headers)
    visita = await _create_visita(client, headers, contacto["id"], vendedor["id"])

    response = await client.post(
        "/crm/oportunidades", json={"contacto_id": contacto["id"], "visita_id": visita["id"]}, headers=headers
    )
    assert response.status_code == 201
    assert response.json()["visita_id"] == visita["id"]


async def test_rechazo_primera_compra_sin_erp_vinculado(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)
    oportunidad = (
        await client.post("/crm/oportunidades", json={"contacto_id": contacto["id"]}, headers=headers)
    ).json()

    response = await client.put(
        f"/crm/oportunidades/{oportunidad['id']}/etapa", json={"etapa_nombre": "Primera Compra"}, headers=headers
    )
    assert response.status_code == 400


async def test_primera_compra_permitida_con_compra_erp(client, auth_header, session):
    headers = await auth_header("vendedor")

    session.add(Clientes(id=555, nom1="Cliente ERP"))
    await session.commit()
    await session.execute(
        text(
            "INSERT INTO panacea_sales_v2 (document_id, customer_id, product_id, count, subtotal, operation_date) "
            "VALUES (1, 555, 1, 1, 100, CURRENT_DATE)"
        )
    )
    await session.commit()

    contacto = await _create_contacto(client, headers, erp_cliente_id=555)
    oportunidad = (
        await client.post("/crm/oportunidades", json={"contacto_id": contacto["id"]}, headers=headers)
    ).json()

    response = await client.put(
        f"/crm/oportunidades/{oportunidad['id']}/etapa", json={"etapa_nombre": "Primera Compra"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["etapa_nombre"] == "Primera Compra"


async def test_actividades_ordenadas_por_fecha(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)
    oportunidad = (
        await client.post("/crm/oportunidades", json={"contacto_id": contacto["id"]}, headers=headers)
    ).json()

    await client.post(
        f"/crm/oportunidades/{oportunidad['id']}/actividades",
        json={"tipo": "llamada", "fecha": "2026-02-01"},
        headers=headers,
    )
    await client.post(
        f"/crm/oportunidades/{oportunidad['id']}/actividades",
        json={"tipo": "email", "fecha": "2026-01-01"},
        headers=headers,
    )

    response = await client.get(f"/crm/oportunidades/{oportunidad['id']}/actividades", headers=headers)
    fechas = [a["fecha"] for a in response.json()]
    assert fechas == sorted(fechas)


async def test_cambio_de_etapa_queda_auditado(client, auth_header, session):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)
    oportunidad = (
        await client.post("/crm/oportunidades", json={"contacto_id": contacto["id"]}, headers=headers)
    ).json()

    await client.put(
        f"/crm/oportunidades/{oportunidad['id']}/etapa", json={"etapa_nombre": "Visita"}, headers=headers
    )

    result = await session.execute(
        select(CrmAuditoria).where(CrmAuditoria.entidad == "Oportunidad", CrmAuditoria.campo == "etapa")
    )
    entry = result.scalar_one()
    assert entry.valor_anterior == "Lead"
    assert entry.valor_nuevo == "Visita"
