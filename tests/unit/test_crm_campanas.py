from datetime import date


async def _create_contacto(client, headers, nombre="Juan") -> dict:
    response = await client.post("/crm/contactos", json={"tipo": "B2C", "nombre": nombre}, headers=headers)
    assert response.status_code == 201
    return response.json()


async def _create_campana(client, headers, **overrides) -> dict:
    payload = {"nombre": "Verano 2026", "fecha_inicio": date.today().isoformat()}
    payload.update(overrides)
    response = await client.post("/crm/campanas", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


async def test_create_campana_con_fechas(client, auth_header):
    headers = await auth_header("marketing")
    response = await client.post(
        "/crm/campanas",
        json={"nombre": "Verano", "fecha_inicio": "2026-01-01", "fecha_fin": "2026-02-28"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["fecha_fin"] == "2026-02-28"


async def test_create_campana_sin_fecha_fin(client, auth_header):
    headers = await auth_header("marketing")
    campana = await _create_campana(client, headers)
    assert campana["fecha_fin"] is None


async def test_contacto_asociado_a_multiples_campanas(client, auth_header):
    headers = await auth_header("marketing")
    contacto = await _create_contacto(client, headers)
    campana_a = await _create_campana(client, headers, nombre="Campana A")
    campana_b = await _create_campana(client, headers, nombre="Campana B")

    r1 = await client.post(
        f"/crm/campanas/{campana_a['id']}/contactos", json={"contacto_id": contacto["id"]}, headers=headers
    )
    r2 = await client.post(
        f"/crm/campanas/{campana_b['id']}/contactos", json={"contacto_id": contacto["id"]}, headers=headers
    )
    assert r1.status_code == 201
    assert r2.status_code == 201


async def test_asociacion_duplicada_es_idempotente(client, auth_header, session):
    from sqlalchemy import select

    from app.models.crm_campana import CrmContactoCampana

    headers = await auth_header("marketing")
    contacto = await _create_contacto(client, headers)
    campana = await _create_campana(client, headers)

    await client.post(f"/crm/campanas/{campana['id']}/contactos", json={"contacto_id": contacto["id"]}, headers=headers)
    response = await client.post(
        f"/crm/campanas/{campana['id']}/contactos", json={"contacto_id": contacto["id"]}, headers=headers
    )
    assert response.status_code == 201

    result = await session.execute(
        select(CrmContactoCampana).where(
            CrmContactoCampana.campana_id == campana["id"], CrmContactoCampana.contacto_id == contacto["id"]
        )
    )
    assert len(result.scalars().all()) == 1


async def test_conversion_cuenta_contactos_con_erp_vinculado(client, auth_header):
    headers = await auth_header("marketing")
    contacto_sin_erp = await _create_contacto(client, headers, nombre="Sin ERP")
    campana = await _create_campana(client, headers)

    await client.post(
        f"/crm/campanas/{campana['id']}/contactos", json={"contacto_id": contacto_sin_erp["id"]}, headers=headers
    )

    response = await client.get(f"/crm/campanas/{campana['id']}/conversion", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["contactos_asociados"] == 1
    assert body["contactos_con_erp"] == 0
