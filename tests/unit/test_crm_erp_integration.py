from sqlalchemy import text

from app.main import app
from app.models.clientes import Clientes


async def _create_contacto(client, headers, **overrides) -> dict:
    payload = {"tipo": "B2C", "nombre": "Juan"}
    payload.update(overrides)
    response = await client.post("/crm/contactos", json=payload, headers=headers)
    return response.json()


async def _seed_cliente_con_compras(session, cliente_id: int, email: str | None = None) -> None:
    session.add(Clientes(id=cliente_id, nom1="Cliente ERP", email1=email))
    await session.commit()
    await session.execute(
        text(
            "INSERT INTO panacea_sales_v2 (document_id, customer_id, product_id, product, count, subtotal, operation_date) "
            "VALUES (:doc, :cid, 1, 'Pan Frances', 10, 1000, CURRENT_DATE)"
        ),
        {"doc": cliente_id, "cid": cliente_id},
    )
    await session.commit()


async def test_link_erp_cliente_valido(client, auth_header, session):
    headers = await auth_header("vendedor")
    await _seed_cliente_con_compras(session, 601)
    contacto = await _create_contacto(client, headers)

    response = await client.put(
        f"/crm/contactos/{contacto['id']}/erp-cliente", json={"erp_cliente_id": 601}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["erp_cliente_id"] == 601


async def test_link_erp_cliente_inexistente_es_rechazado(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)

    response = await client.put(
        f"/crm/contactos/{contacto['id']}/erp-cliente", json={"erp_cliente_id": 999999}, headers=headers
    )
    assert response.status_code == 400


async def test_autovincular_por_email(client, auth_header, session):
    headers = await auth_header("vendedor")
    await _seed_cliente_con_compras(session, 602, email="match@example.com")
    contacto = await _create_contacto(client, headers, email="match@example.com")

    response = await client.post("/crm/contactos/autovincular-erp", headers=headers)
    assert response.status_code == 200
    assert contacto["id"] in response.json()["contactos_vinculados"]

    updated = await client.get(f"/crm/contactos/{contacto['id']}", headers=headers)
    assert updated.json()["erp_cliente_id"] == 602


async def test_historial_compras_vacio_sin_erp(client, auth_header):
    headers = await auth_header("vendedor")
    contacto = await _create_contacto(client, headers)

    response = await client.get(f"/crm/contactos/{contacto['id']}/compras", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_productos_mas_consumidos_ordenado_por_consumo(client, auth_header, session):
    headers = await auth_header("vendedor")
    session.add(Clientes(id=603, nom1="Cliente ERP"))
    await session.commit()
    await session.execute(
        text(
            "INSERT INTO panacea_sales_v2 (document_id, customer_id, product_id, product, count, subtotal, operation_date) VALUES "
            "(1, 603, 1, 'Pan Frances', 5, 500, CURRENT_DATE), "
            "(2, 603, 2, 'Facturas', 20, 800, CURRENT_DATE)"
        )
    )
    await session.commit()
    contacto = await _create_contacto(client, headers, erp_cliente_id=603)

    response = await client.get(f"/crm/contactos/{contacto['id']}/productos-mas-consumidos", headers=headers)
    assert response.status_code == 200
    productos = response.json()
    assert productos[0]["product"] == "Facturas"


def test_no_crm_router_writes_to_clientes_or_sales():
    for route in app.routes:
        tags = getattr(route, "tags", None) or []
        if not any(str(tag).startswith("crm-") for tag in tags):
            continue
        methods = getattr(route, "methods", set()) or set()
        write_methods = methods & {"POST", "PUT", "PATCH", "DELETE"}
        if not write_methods:
            continue
        # CRM write endpoints only ever set crm_contacto.erp_cliente_id (a
        # foreign key value) — none targets /clientes or /sales* directly,
        # which is what would indicate the CRM writing into ERP-owned
        # sales tables instead of only reading them (RN-001).
        path = route.path.lower()
        assert not path.startswith("/clientes")
        assert "/sales" not in path
