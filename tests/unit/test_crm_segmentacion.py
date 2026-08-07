from app.config import get_settings


async def _create_contacto(client, headers, nombre, **overrides) -> dict:
    payload = {"tipo": "B2C", "nombre": nombre}
    payload.update(overrides)
    response = await client.post("/crm/contactos", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


async def _create_ciudad(client, headers, nombre="Cordoba") -> dict:
    response = await client.post("/crm/catalogos/ciudades", json={"nombre": nombre}, headers=headers)
    assert response.status_code == 201
    return response.json()


async def test_create_segmento_con_criterio(client, auth_header):
    headers = await auth_header("marketing")
    response = await client.post(
        "/crm/segmentos", json={"nombre": "Cordoba", "criterio": {"ciudad_id": 1}}, headers=headers
    )
    assert response.status_code == 201
    assert response.json()["criterio"] == {"ciudad_id": 1}


async def test_recompute_agrega_contactos_que_cumplen_criterio(client, auth_header):
    headers = await auth_header("marketing")
    ciudad = await _create_ciudad(client, headers)
    contacto = await _create_contacto(client, headers, "En Cordoba", ciudad_id=ciudad["id"])
    await _create_contacto(client, headers, "En otro lado")

    segmento = (
        await client.post(
            "/crm/segmentos", json={"nombre": "De Cordoba", "criterio": {"ciudad_id": ciudad["id"]}}, headers=headers
        )
    ).json()

    response = await client.post("/crm/segmentos/recompute", headers=headers)
    assert response.status_code == 200
    assert response.json()["counts"][str(segmento["id"])] == 1

    miembros = await client.get(f"/crm/segmentos/{segmento['id']}/miembros", headers=headers)
    assert [m["contacto_id"] for m in miembros.json()] == [contacto["id"]]


async def test_recompute_remueve_contactos_que_dejan_de_cumplir(client, auth_header):
    headers = await auth_header("marketing")
    ciudad = await _create_ciudad(client, headers)
    contacto = await _create_contacto(client, headers, "En Cordoba", ciudad_id=ciudad["id"])
    segmento = (
        await client.post(
            "/crm/segmentos", json={"nombre": "De Cordoba", "criterio": {"ciudad_id": ciudad["id"]}}, headers=headers
        )
    ).json()
    await client.post("/crm/segmentos/recompute", headers=headers)

    await client.put(
        f"/crm/contactos/{contacto['id']}", json={"tipo": "B2C", "nombre": "En Cordoba"}, headers=headers
    )
    await client.post("/crm/segmentos/recompute", headers=headers)

    miembros = await client.get(f"/crm/segmentos/{segmento['id']}/miembros", headers=headers)
    assert miembros.json() == []


async def test_recompute_manual_no_requiere_rol_especifico(client, auth_header):
    # require_role(*CRM_ROLES) was replaced by require_authenticated(): any
    # valid session can trigger a manual recompute now.
    headers = await auth_header("user")
    response = await client.post("/crm/segmentos/recompute", headers=headers)
    assert response.status_code == 200


async def test_recompute_actualiza_timestamp(client, auth_header):
    headers = await auth_header("marketing")
    ciudad = await _create_ciudad(client, headers)
    await _create_contacto(client, headers, "En Cordoba", ciudad_id=ciudad["id"])
    segmento = (
        await client.post(
            "/crm/segmentos", json={"nombre": "De Cordoba", "criterio": {"ciudad_id": ciudad["id"]}}, headers=headers
        )
    ).json()

    await client.post("/crm/segmentos/recompute", headers=headers)
    first = (await client.get(f"/crm/segmentos/{segmento['id']}/miembros", headers=headers)).json()[0]

    await client.post("/crm/segmentos/recompute", headers=headers)
    second = (await client.get(f"/crm/segmentos/{segmento['id']}/miembros", headers=headers)).json()[0]

    assert second["recalculado_en"] >= first["recalculado_en"]


async def test_cron_recompute_requires_cron_secret(client):
    response = await client.post("/internal/cron/crm-recompute-segmentos")
    assert response.status_code == 401


async def test_cron_recompute_works_with_valid_secret(client, auth_header, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-cron-secret")
    get_settings.cache_clear()
    try:
        headers = await auth_header("marketing")
        ciudad = await _create_ciudad(client, headers)
        await _create_contacto(client, headers, "En Cordoba", ciudad_id=ciudad["id"])
        await client.post(
            "/crm/segmentos", json={"nombre": "De Cordoba", "criterio": {"ciudad_id": ciudad["id"]}}, headers=headers
        )

        response = await client.post(
            "/internal/cron/crm-recompute-segmentos", headers={"Authorization": "Bearer test-cron-secret"}
        )
        assert response.status_code == 200
        assert response.json()["segmentos_recalculados"] == 1
    finally:
        get_settings.cache_clear()
