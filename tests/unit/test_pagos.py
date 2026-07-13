from datetime import date


async def _create_proveedor(client) -> dict:
    response = await client.post("/costos/proveedores", json={"nombre": "Galicia SA", "cuit": "20-66666666-6"})
    assert response.status_code == 201
    return response.json()


async def _create_compra(client, proveedor_id: int, **overrides) -> dict:
    payload = {
        "proveedor_id": proveedor_id,
        "tipo_comprobante": "FACTURA_A",
        "numero": "1",
        "fecha": date.today().isoformat(),
        "condicion_pago": "CUENTA_CORRIENTE",
        "detalle": [{"descripcion": "Item", "cantidad": 1, "precio_unitario": 1000}],
    }
    payload.update(overrides)
    response = await client.post("/costos/compras", json=payload)
    assert response.status_code == 201
    return response.json()


async def test_create_pago_with_single_medio(client):
    proveedor = await _create_proveedor(client)
    response = await client.post(
        "/costos/pagos",
        json={
            "proveedor_id": proveedor["id"],
            "fecha": date.today().isoformat(),
            "importe": 500,
            "medios": [{"tipo": "EFECTIVO", "importe": 500}],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["importe"] == 500
    assert len(body["medios"]) == 1
    assert body["proveedor_nombre"] == "Galicia SA"

    listed = (await client.get("/costos/pagos")).json()
    assert next(p for p in listed if p["id"] == body["id"])["proveedor_nombre"] == "Galicia SA"


async def test_reject_mismatched_medios_total(client):
    proveedor = await _create_proveedor(client)
    response = await client.post(
        "/costos/pagos",
        json={
            "proveedor_id": proveedor["id"],
            "fecha": date.today().isoformat(),
            "importe": 500,
            "medios": [{"tipo": "EFECTIVO", "importe": 300}],
        },
    )
    assert response.status_code == 400


async def test_split_pago_across_transferencia_and_cheque(client):
    proveedor = await _create_proveedor(client)
    response = await client.post(
        "/costos/pagos",
        json={
            "proveedor_id": proveedor["id"],
            "fecha": date.today().isoformat(),
            "importe": 1000,
            "medios": [
                {"tipo": "TRANSFERENCIA", "importe": 500},
                {
                    "tipo": "CHEQUE",
                    "importe": 500,
                    "banco": "Galicia",
                    "numero": "123",
                    "fecha_acreditacion": date.today().isoformat(),
                },
            ],
        },
    )
    assert response.status_code == 201
    assert len(response.json()["medios"]) == 2


async def test_reject_cheque_medio_missing_banking_fields(client):
    proveedor = await _create_proveedor(client)
    response = await client.post(
        "/costos/pagos",
        json={
            "proveedor_id": proveedor["id"],
            "fecha": date.today().isoformat(),
            "importe": 500,
            "medios": [{"tipo": "CHEQUE", "importe": 500}],
        },
    )
    assert response.status_code == 400


async def test_apply_pago_to_multiple_compras_updates_saldo_via_trigger(client):
    proveedor = await _create_proveedor(client)
    compra1 = await _create_compra(client, proveedor["id"], numero="1")
    compra2 = await _create_compra(client, proveedor["id"], numero="2")
    assert compra1["saldo_pendiente"] == 1000
    assert compra2["saldo_pendiente"] == 1000

    pago = (
        await client.post(
            "/costos/pagos",
            json={
                "proveedor_id": proveedor["id"],
                "fecha": date.today().isoformat(),
                "importe": 1500,
                "medios": [{"tipo": "TRANSFERENCIA", "importe": 1500}],
            },
        )
    ).json()

    response = await client.post(
        f"/costos/pagos/{pago['id']}/aplicaciones",
        json=[
            {"compra_id": compra1["id"], "importe": 1000},
            {"compra_id": compra2["id"], "importe": 500},
        ],
    )
    assert response.status_code == 201
    assert len(response.json()) == 2
    assert {a["comprobante"] for a in response.json()} == {
        "FACTURA_A:0000-00000001",
        "FACTURA_A:0000-00000002",
    }

    # The DB trigger (not application code) must have decremented both
    # compras' saldo_pendiente and updated estado.
    compra1_after = (await client.get(f"/costos/compras/{compra1['id']}")).json()
    compra2_after = (await client.get(f"/costos/compras/{compra2['id']}")).json()
    assert compra1_after["saldo_pendiente"] == 0
    assert compra1_after["estado"] == "PAGADO"
    assert compra2_after["saldo_pendiente"] == 500
    assert compra2_after["estado"] == "PARCIAL"

    pagos_for_compra1 = await client.get(f"/costos/compras/{compra1['id']}/pagos")
    assert pagos_for_compra1.status_code == 200
    assert [p["id"] for p in pagos_for_compra1.json()] == [pago["id"]]

    aplicaciones = await client.get(f"/costos/pagos/{pago['id']}/aplicaciones")
    assert aplicaciones.status_code == 200
    assert {(a["compra_id"], a["importe"], a["comprobante"]) for a in aplicaciones.json()} == {
        (compra1["id"], 1000, "FACTURA_A:0000-00000001"),
        (compra2["id"], 500, "FACTURA_A:0000-00000002"),
    }


async def test_list_aplicaciones_for_missing_pago_returns_404(client):
    response = await client.get("/costos/pagos/999999/aplicaciones")
    assert response.status_code == 404


async def test_list_pagos_orders_most_recent_first(client):
    proveedor = await _create_proveedor(client)

    async def _create_pago(fecha: date) -> dict:
        response = await client.post(
            "/costos/pagos",
            json={
                "proveedor_id": proveedor["id"],
                "fecha": fecha.isoformat(),
                "importe": 100,
                "medios": [{"tipo": "EFECTIVO", "importe": 100}],
            },
        )
        assert response.status_code == 201
        return response.json()

    older = await _create_pago(date(2026, 1, 1))
    newer = await _create_pago(date(2026, 6, 1))

    listed = (await client.get("/costos/pagos", params={"proveedor_id": proveedor["id"]})).json()
    assert [p["id"] for p in listed] == [newer["id"], older["id"]]
