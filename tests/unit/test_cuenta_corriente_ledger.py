from datetime import date


async def _create_proveedor(client) -> dict:
    response = await client.post("/costos/proveedores", json={"nombre": "Andreani", "cuit": "20-77777777-7"})
    assert response.status_code == 201
    return response.json()


async def _create_compra(client, proveedor_id: int, total_precio: float, **overrides) -> dict:
    payload = {
        "proveedor_id": proveedor_id,
        "tipo_comprobante": "FACTURA_A",
        "numero": "1",
        "fecha": date.today().isoformat(),
        "condicion_pago": "CUENTA_CORRIENTE",
        "detalle": [{"descripcion": "Item", "cantidad": 1, "precio_unitario": total_precio}],
    }
    payload.update(overrides)
    response = await client.post("/costos/compras", json=payload)
    assert response.status_code == 201
    return response.json()


async def test_compra_and_pago_produce_matching_movimientos_and_running_saldo(client):
    proveedor = await _create_proveedor(client)
    compra = await _create_compra(client, proveedor["id"], 1000, numero="F1")

    pago = (
        await client.post(
            "/costos/pagos",
            json={
                "proveedor_id": proveedor["id"],
                "fecha": date.today().isoformat(),
                "importe": 400,
                "medios": [{"tipo": "EFECTIVO", "importe": 400}],
            },
        )
    ).json()
    await client.post(
        f"/costos/pagos/{pago['id']}/aplicaciones", json=[{"compra_id": compra["id"], "importe": 400}]
    )

    ledger = await client.get(f"/costos/proveedores/{proveedor['id']}/cuenta-corriente")
    assert ledger.status_code == 200
    movimientos = ledger.json()["movimientos"]
    assert len(movimientos) == 2
    assert movimientos[0]["tipo"] == "FACTURA"
    assert movimientos[0]["debe"] == 1000
    assert movimientos[0]["saldo"] == 1000
    assert movimientos[1]["tipo"] == "PAGO"
    assert movimientos[1]["haber"] == 400
    assert movimientos[1]["saldo"] == 600


async def test_saldo_pendiente_agrees_with_ledger_derived_balance(client):
    proveedor = await _create_proveedor(client)
    compra1 = await _create_compra(client, proveedor["id"], 1000, numero="F1")
    compra2 = await _create_compra(client, proveedor["id"], 500, numero="F2")

    pago = (
        await client.post(
            "/costos/pagos",
            json={
                "proveedor_id": proveedor["id"],
                "fecha": date.today().isoformat(),
                "importe": 300,
                "medios": [{"tipo": "TRANSFERENCIA", "importe": 300}],
            },
        )
    ).json()
    await client.post(
        f"/costos/pagos/{pago['id']}/aplicaciones", json=[{"compra_id": compra1["id"], "importe": 300}]
    )

    compra1_after = (await client.get(f"/costos/compras/{compra1['id']}")).json()
    compra2_after = (await client.get(f"/costos/compras/{compra2['id']}")).json()
    sum_saldo_pendiente = compra1_after["saldo_pendiente"] + compra2_after["saldo_pendiente"]

    ledger = (await client.get(f"/costos/proveedores/{proveedor['id']}/cuenta-corriente")).json()
    ledger_saldo = ledger["movimientos"][-1]["saldo"]

    assert sum_saldo_pendiente == ledger_saldo == 1200


async def test_resumen_endpoint(client):
    proveedor = await _create_proveedor(client)
    today = date.today().isoformat()
    await _create_compra(client, proveedor["id"], 1000, numero="F1", fecha=today)
    await _create_compra(client, proveedor["id"], 200, numero="F2", fecha=today, condicion_pago="CONTADO")
    await client.post(
        "/costos/pagos",
        json={
            "proveedor_id": proveedor["id"],
            "fecha": today,
            "importe": 350,
            "medios": [{"tipo": "EFECTIVO", "importe": 350}],
        },
    )

    response = await client.get("/costos/cuenta-corriente/resumen", params={"fecha_desde": today, "fecha_hasta": today})
    assert response.status_code == 200
    body = response.json()
    assert body["total_facturas_pendientes"] == 1000
    # total_gastos is every compra in the period regardless of
    # condicion_pago/estado — not just the ones already paid off.
    assert body["total_gastos"] == 1200
    assert body["total_pagos"] == 350


async def test_resumen_gastos_y_pagos_por_categoria(client):
    proveedor = await _create_proveedor(client)
    today = date.today().isoformat()
    compra_mp = await _create_compra(client, proveedor["id"], 1000, numero="F1", fecha=today, categoria="MATERIA_PRIMA")
    await _create_compra(client, proveedor["id"], 200, numero="F2", fecha=today, categoria="SERVICIOS")

    pago = (
        await client.post(
            "/costos/pagos",
            json={
                "proveedor_id": proveedor["id"],
                "fecha": today,
                "importe": 400,
                "medios": [{"tipo": "EFECTIVO", "importe": 400}],
            },
        )
    ).json()
    await client.post(
        f"/costos/pagos/{pago['id']}/aplicaciones", json=[{"compra_id": compra_mp["id"], "importe": 400}]
    )

    response = await client.get("/costos/cuenta-corriente/resumen", params={"fecha_desde": today, "fecha_hasta": today})
    assert response.status_code == 200
    body = response.json()

    gastos_por_id = {r["categoria"]: r["total"] for r in body["gastos_por_categoria"]}
    assert gastos_por_id == {"MATERIA_PRIMA": 1000, "SERVICIOS": 200}

    # Solo la Compra efectivamente saldada por el pago aparece — el pago se
    # atribuye a la categoria de la Compra que aplica, no tiene la suya propia.
    pagos_por_id = {r["categoria"]: r["total"] for r in body["pagos_por_categoria"]}
    assert pagos_por_id == {"MATERIA_PRIMA": 400}


async def test_resumen_gastos_and_pagos_are_scoped_to_period(client):
    proveedor = await _create_proveedor(client)
    await _create_compra(client, proveedor["id"], 1000, numero="F1", fecha="2026-01-15")
    await client.post(
        "/costos/pagos",
        json={
            "proveedor_id": proveedor["id"],
            "fecha": "2026-01-15",
            "importe": 500,
            "medios": [{"tipo": "EFECTIVO", "importe": 500}],
        },
    )

    response = await client.get(
        "/costos/cuenta-corriente/resumen",
        params={"fecha_desde": "2026-02-01", "fecha_hasta": "2026-02-28"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_gastos"] == 0
    assert body["total_pagos"] == 0
    # facturas_pendientes is not period-scoped, so it still reflects the
    # January compra's outstanding balance.
    assert body["total_facturas_pendientes"] == 1000


async def test_saldos_endpoint_groups_by_proveedor(client):
    proveedor_a = await _create_proveedor(client)
    proveedor_b_response = await client.post(
        "/costos/proveedores", json={"nombre": "Bertotto", "cuit": "20-66666666-6"}
    )
    assert proveedor_b_response.status_code == 201
    proveedor_b = proveedor_b_response.json()

    await _create_compra(client, proveedor_a["id"], 1000, numero="F1")
    await _create_compra(client, proveedor_a["id"], 500, numero="F2")
    await _create_compra(client, proveedor_b["id"], 300, numero="F1")
    # CONTADO compras are settled immediately and must not contribute to saldos.
    await _create_compra(client, proveedor_b["id"], 999, numero="T1", condicion_pago="CONTADO")

    response = await client.get("/costos/cuenta-corriente/saldos")
    assert response.status_code == 200
    body = response.json()
    assert body["total_pendiente"] == 1800

    saldos_por_id = {p["proveedor_id"]: p["saldo"] for p in body["proveedores"]}
    assert saldos_por_id[proveedor_a["id"]] == 1500
    assert saldos_por_id[proveedor_b["id"]] == 300


async def test_gastos_por_proveedor_ranked_descending_and_scoped_to_period(client):
    proveedor_a = await _create_proveedor(client)
    proveedor_b_response = await client.post(
        "/costos/proveedores", json={"nombre": "Bertotto", "cuit": "20-66666666-6"}
    )
    assert proveedor_b_response.status_code == 201
    proveedor_b = proveedor_b_response.json()

    today = date.today().isoformat()
    await _create_compra(client, proveedor_a["id"], 500, numero="F1", fecha=today)
    await _create_compra(client, proveedor_b["id"], 1000, numero="F1", fecha=today)
    # Out of period — must not contribute to the ranking.
    await _create_compra(client, proveedor_a["id"], 5000, numero="F2", fecha="2020-01-01")

    response = await client.get(
        "/costos/cuenta-corriente/gastos-por-proveedor", params={"fecha_desde": today, "fecha_hasta": today}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_periodo"] == 1500

    nombres = [p["proveedor_nombre"] for p in body["proveedores"]]
    assert nombres == ["Bertotto", proveedor_a["nombre"]]  # descending by total
    totales = {p["proveedor_nombre"]: p["total"] for p in body["proveedores"]}
    assert totales == {"Bertotto": 1000, proveedor_a["nombre"]: 500}


async def test_pagos_por_proveedor_ranked_descending_and_scoped_to_period(client):
    proveedor_a = await _create_proveedor(client)
    proveedor_b_response = await client.post(
        "/costos/proveedores", json={"nombre": "Bertotto", "cuit": "20-66666666-6"}
    )
    assert proveedor_b_response.status_code == 201
    proveedor_b = proveedor_b_response.json()

    today = date.today().isoformat()
    for proveedor_id, importe in ((proveedor_a["id"], 300), (proveedor_b["id"], 900)):
        await client.post(
            "/costos/pagos",
            json={
                "proveedor_id": proveedor_id,
                "fecha": today,
                "importe": importe,
                "medios": [{"tipo": "EFECTIVO", "importe": importe}],
            },
        )
    # Out of period — must not contribute to the ranking.
    await client.post(
        "/costos/pagos",
        json={
            "proveedor_id": proveedor_a["id"],
            "fecha": "2020-01-01",
            "importe": 9000,
            "medios": [{"tipo": "EFECTIVO", "importe": 9000}],
        },
    )

    response = await client.get(
        "/costos/cuenta-corriente/pagos-por-proveedor", params={"fecha_desde": today, "fecha_hasta": today}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_periodo"] == 1200

    nombres = [p["proveedor_nombre"] for p in body["proveedores"]]
    assert nombres == ["Bertotto", proveedor_a["nombre"]]  # descending by total
    totales = {p["proveedor_nombre"]: p["total"] for p in body["proveedores"]}
    assert totales == {"Bertotto": 900, proveedor_a["nombre"]: 300}


async def test_saldos_endpoint_excludes_proveedor_sin_saldo_pendiente(client):
    proveedor = await _create_proveedor(client)
    compra = await _create_compra(client, proveedor["id"], 1000, numero="F1")

    pago = (
        await client.post(
            "/costos/pagos",
            json={
                "proveedor_id": proveedor["id"],
                "fecha": date.today().isoformat(),
                "importe": 1000,
                "medios": [{"tipo": "EFECTIVO", "importe": 1000}],
            },
        )
    ).json()
    await client.post(
        f"/costos/pagos/{pago['id']}/aplicaciones", json=[{"compra_id": compra["id"], "importe": 1000}]
    )

    response = await client.get("/costos/cuenta-corriente/saldos")
    assert response.status_code == 200
    ids = {p["proveedor_id"] for p in response.json()["proveedores"]}
    assert proveedor["id"] not in ids
