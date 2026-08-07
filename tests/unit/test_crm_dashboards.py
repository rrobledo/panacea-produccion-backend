from datetime import date, timedelta

from sqlalchemy import text

from app.models.clientes import Clientes


async def _create_contacto(client, headers, **overrides) -> dict:
    payload = {"tipo": "B2C", "nombre": "Juan"}
    payload.update(overrides)
    response = await client.post("/crm/contactos", json=payload, headers=headers)
    return response.json()


async def _seed_venta(session, cliente_id: int, subtotal: float = 1000, operation_date: date | None = None, product="Pan"):
    exists = await session.get(Clientes, cliente_id)
    if exists is None:
        session.add(Clientes(id=cliente_id, nom1=f"Cliente {cliente_id}"))
        await session.commit()
    await session.execute(
        text(
            "INSERT INTO panacea_sales_v2 (document_id, customer_id, product_id, product, count, subtotal, operation_date) "
            "VALUES (:doc, :cid, 1, :product, 1, :subtotal, :fecha)"
        ),
        {"doc": cliente_id * 10 + 1, "cid": cliente_id, "product": product, "subtotal": subtotal, "fecha": operation_date or date.today()},
    )
    await session.commit()


async def test_dashboard_ejecutivo_no_requiere_rol_especifico(client, auth_header):
    # CRM endpoints only require a valid session now, not a specific role
    # (require_role(*EJECUTIVO_ROLES) was replaced by require_authenticated()).
    headers = await auth_header("vendedor")
    response = await client.get("/crm/dashboards/ejecutivo", headers=headers)
    assert response.status_code == 200


async def test_dashboard_ejecutivo_devuelve_kpis(client, auth_header, session):
    headers = await auth_header("gerencia")
    await _seed_venta(session, 701)

    response = await client.get("/crm/dashboards/ejecutivo", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "conversion_visitas_clientes" in body
    assert "cac" in body


async def test_dashboard_vendedor_propio(client, auth_header, session):
    headers = await auth_header("vendedor")
    vendedor = (await client.post("/crm/vendedores", json={"nombre": "Carlos"}, headers=headers)).json()

    response = await client.get(f"/crm/dashboards/vendedor/{vendedor['id']}", headers=headers)
    # own dashboard: not linked via user_id, so treated as "not this vendedor" -> 403
    assert response.status_code == 403


async def test_dashboard_vendedor_ajeno_rechazado_para_supervisor_ve_cualquiera(client, auth_header):
    headers_sup = await auth_header("supervisor_comercial")
    vendedor = (await client.post("/crm/vendedores", json={"nombre": "Carlos"}, headers=headers_sup)).json()

    response = await client.get(f"/crm/dashboards/vendedor/{vendedor['id']}", headers=headers_sup)
    assert response.status_code == 200
    assert response.json()["vendedor_id"] == vendedor["id"]


async def test_dashboard_marketing(client, auth_header):
    headers = await auth_header("marketing")
    await client.post(
        "/crm/campanas", json={"nombre": "Verano", "fecha_inicio": date.today().isoformat(), "costo": 1000}, headers=headers
    )

    response = await client.get("/crm/dashboards/marketing", headers=headers)
    assert response.status_code == 200
    assert len(response.json()["campanas"]) == 1


async def test_dashboard_contacto_360_con_erp(client, auth_header, session):
    headers = await auth_header("vendedor")
    await _seed_venta(session, 702, subtotal=500)
    contacto = await _create_contacto(client, headers, erp_cliente_id=702)

    response = await client.get(f"/crm/dashboards/contacto/{contacto['id']}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["contacto"]["id"] == contacto["id"]
    assert body["facturacion_12_meses"] == 500
    assert len(body["ultimas_compras"]) == 1


async def test_dashboard_contacto_360_sin_erp(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)

    response = await client.get(f"/crm/dashboards/contacto/{contacto['id']}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["ultimas_compras"] == []
    assert body["productos_favoritos"] == []
    assert body["facturacion_12_meses"] == 0


async def test_clientes_inactivos_lista_contactos_con_ultima_compra_vieja(client, auth_header, session):
    headers = await auth_header("gerencia")
    await _seed_venta(session, 703, operation_date=date.today() - timedelta(days=100))
    await _create_contacto(client, headers, erp_cliente_id=703)

    response = await client.get("/crm/dashboards/reportes/clientes-inactivos", params={"dias": 60}, headers=headers)
    assert response.status_code == 200
    assert any(row["contacto_id"] for row in response.json())


async def test_reporte_ventas_por_segmento_csv(client, auth_header):
    headers = await auth_header("gerencia")
    response = await client.get(
        "/crm/dashboards/reportes/ventas-por-segmento", params={"formato": "csv"}, headers=headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
