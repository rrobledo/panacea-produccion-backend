from datetime import date


async def _create_proveedor(client) -> dict:
    response = await client.post("/costos/proveedores", json={"nombre": "YPF", "cuit": "20-88888888-8"})
    assert response.status_code == 201
    return response.json()


async def test_fetch_report_pivots_detalle_and_impuestos_by_tipo(client):
    proveedor = await _create_proveedor(client)
    fecha = date(2026, 7, 15).isoformat()
    await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "1",
            "fecha": fecha,
            "detalle": [{"descripcion": "Harina", "cantidad": 10, "precio_unitario": 1000, "alicuota_iva": 21}],
            "impuestos": [{"tipo": "PERCEPCION_IVA", "importe": 210}],
        },
    )

    response = await client.get("/costos/libro-iva-compras", params={"periodo": "2026-07"})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["neto"] == 10000
    assert row["iva_21"] == 2100
    assert row["percepcion_iva"] == 210
    assert row["sin_discriminar"] == 0


async def test_historical_compra_reports_as_undiscriminated_not_fabricated(client):
    proveedor = await _create_proveedor(client)
    fecha = date(2026, 7, 20).isoformat()
    await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "2",
            "fecha": fecha,
            "impuestos": [{"tipo": "HISTORICO_SIN_DESGLOSE", "importe": 500}],
        },
    )

    response = await client.get("/costos/libro-iva-compras", params={"periodo": "2026-07"})
    assert response.status_code == 200
    row = response.json()[0]
    assert row["sin_discriminar"] == 500
    assert row["iva_21"] == 0
    assert row["iva_10_5"] == 0
    assert row["iva_27"] == 0
    assert row["percepcion_iva"] == 0
    assert row["percepcion_iibb"] == 0


async def test_reject_invalid_periodo_format(client):
    response = await client.get("/costos/libro-iva-compras", params={"periodo": "not-a-period"})
    assert response.status_code == 400
