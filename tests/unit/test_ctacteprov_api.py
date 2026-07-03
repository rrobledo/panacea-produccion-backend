from datetime import date

from app.deps import require_api_key
from app.main import app


async def test_create_proveedor_and_duplicate_cuit_is_rejected(client):
    payload = {"nombre": "ABC Fiambres", "cuit": "20-99999999-9"}
    response = await client.post("/costos/proveedores", json=payload)
    assert response.status_code == 201
    assert response.json()["estado"] == "activo"

    duplicate = await client.post("/costos/proveedores", json=payload)
    assert duplicate.status_code == 409


async def test_write_without_api_key_is_rejected(client):
    app.dependency_overrides.pop(require_api_key, None)
    response = await client.post("/costos/proveedores", json={"nombre": "X", "cuit": "1"})
    assert response.status_code == 401


async def test_create_factura_via_http_and_list_pagos(client):
    proveedor_response = await client.post(
        "/costos/proveedores", json={"nombre": "Proveedor HTTP", "cuit": "30-1-1"}
    )
    proveedor = proveedor_response.json()

    factura = await client.post(
        "/costos/ctacteprov",
        json={
            "proveedor": proveedor["id"],
            "tipo_movimiento": "FACTURA",
            "numero": "F1",
            "fecha_emision": date.today().isoformat(),
            "importe_total": 100,
            "tipo_pago": "CUENTA_CORRIENTE",
        },
    )
    assert factura.status_code == 201
    body = factura.json()
    assert body["importe_pendiente"] == 100
    assert body["proveedor_id"] == str(proveedor["id"])

    pagos = await client.get(f"/costos/ctacteprov/{body['id']}/pagos")
    assert pagos.status_code == 200
    assert pagos.json() == []


async def test_resumen_aggregates_pendientes_and_gastos_correctly(client):
    proveedor = (
        await client.post("/costos/proveedores", json={"nombre": "Proveedor Resumen", "cuit": "40-1-1"})
    ).json()
    today = date.today().isoformat()
    out_of_range = date(2020, 1, 1).isoformat()

    async def create(**overrides):
        payload = {
            "proveedor": proveedor["id"],
            "tipo_movimiento": "FACTURA",
            "numero": "n",
            "fecha_emision": today,
            "importe_total": 0,
            "tipo_pago": "CUENTA_CORRIENTE",
        }
        payload.update(overrides)
        response = await client.post("/costos/ctacteprov", json=payload)
        assert response.status_code == 201
        return response.json()

    # Unpaid factura on cuenta corriente: always counts toward
    # total_facturas_pendientes, never toward total_gastos.
    await create(numero="a", importe_total=1000, tipo_pago="CUENTA_CORRIENTE")
    # Immediate-payment factura, in range: counts toward total_gastos (200),
    # not toward total_facturas_pendientes (tipo_pago != CUENTA_CORRIENTE).
    await create(numero="b", importe_total=200, tipo_pago="EFECTIVO")
    # Cuenta-corriente factura fully paid off via a linked PAGO: the PAGO's
    # importe_total counts toward total_gastos; the trigger zeroes the
    # factura's importe_pendiente so it drops out of total_facturas_pendientes.
    factura_c = await create(numero="c", importe_total=300, tipo_pago="CUENTA_CORRIENTE")
    await create(
        numero="pago-c", tipo_movimiento="PAGO", importe_total=300, factura_id=factura_c["id"]
    )
    # Cuenta-corriente factura outside the query's date range: still counts
    # toward total_facturas_pendientes (defined independent of date range),
    # excluded from total_gastos.
    await create(numero="d", importe_total=5000, tipo_pago="CUENTA_CORRIENTE", fecha_emision=out_of_range)

    resumen = await client.get(
        "/costos/ctacteprovresumen", params={"fecha_desde": today, "fecha_hasta": today}
    )
    assert resumen.status_code == 200
    body = resumen.json()
    assert body["total_facturas_pendientes"] == 6000
    assert body["total_gastos"] == 500
