from datetime import date


async def _create_proveedor(client, **overrides):
    payload = {"nombre": "Acindar", "cuit": "20-11111111-1"}
    payload.update(overrides)
    response = await client.post("/costos/proveedores", json=payload)
    assert response.status_code == 201
    return response.json()


async def test_create_compra_with_detalle_and_impuestos_computes_totals(client):
    proveedor = await _create_proveedor(client)
    response = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "0001-00000023",
            "fecha": date.today().isoformat(),
            "condicion_pago": "CUENTA_CORRIENTE",
            "detalle": [
                {"descripcion": "Harina", "cantidad": 10, "precio_unitario": 1000, "alicuota_iva": 21}
            ],
            "impuestos": [
                {"tipo": "PERCEPCION_IVA", "importe": 210},
                {"tipo": "PERCEPCION_IIBB", "importe": 150},
            ],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["subtotal"] == 10000
    assert body["iva"] == 2100
    assert body["percepciones"] == 360
    assert body["total"] == 10000 + 2100 + 360
    assert body["saldo_pendiente"] == body["total"]
    assert body["estado"] == "PENDIENTE"
    assert body["proveedor_nombre"] == "Acindar"
    assert len(body["detalle"]) == 1
    assert body["detalle"][0]["importe_total"] == 12100

    listed = (await client.get("/costos/compras")).json()
    assert next(c for c in listed if c["id"] == body["id"])["proveedor_nombre"] == "Acindar"


async def test_contado_compra_is_settled_immediately(client):
    proveedor = await _create_proveedor(client)
    response = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "TICKET",
            "numero": "1",
            "fecha": date.today().isoformat(),
            "condicion_pago": "CONTADO",
            "detalle": [{"descripcion": "Nafta", "cantidad": 1, "precio_unitario": 500}],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["saldo_pendiente"] == 0
    assert body["estado"] == "PAGADO"


async def test_condicion_pago_defaults_from_proveedor(client):
    proveedor = await _create_proveedor(client, condicion_pago="CONTADO")
    response = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "TICKET",
            "numero": "1",
            "fecha": date.today().isoformat(),
            "detalle": [{"descripcion": "Peaje", "cantidad": 1, "precio_unitario": 100}],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["condicion_pago"] == "CONTADO"
    assert body["estado"] == "PAGADO"


async def test_list_compras_filters_by_con_saldo(client):
    proveedor = await _create_proveedor(client)
    pendiente = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "F1",
            "fecha": date.today().isoformat(),
            "condicion_pago": "CUENTA_CORRIENTE",
            "detalle": [{"descripcion": "Harina", "cantidad": 1, "precio_unitario": 1000}],
        },
    )
    assert pendiente.status_code == 201
    pendiente_id = pendiente.json()["id"]

    saldada = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "TICKET",
            "numero": "T1",
            "fecha": date.today().isoformat(),
            "condicion_pago": "CONTADO",
            "detalle": [{"descripcion": "Nafta", "cantidad": 1, "precio_unitario": 500}],
        },
    )
    assert saldada.status_code == 201
    saldada_id = saldada.json()["id"]

    con_saldo = (await client.get("/costos/compras", params={"con_saldo": True})).json()
    assert {c["id"] for c in con_saldo} >= {pendiente_id}
    assert saldada_id not in {c["id"] for c in con_saldo}

    sin_saldo = (await client.get("/costos/compras", params={"con_saldo": False})).json()
    assert {c["id"] for c in sin_saldo} >= {saldada_id}
    assert pendiente_id not in {c["id"] for c in sin_saldo}


async def test_reject_unknown_compra_impuesto_tipo(client):
    proveedor = await _create_proveedor(client)
    response = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "1",
            "fecha": date.today().isoformat(),
            "impuestos": [{"tipo": "IVA_INVENTADO", "importe": 100}],
        },
    )
    assert response.status_code == 400


async def test_add_detalle_recomputes_parent_totals(client):
    proveedor = await _create_proveedor(client)
    created = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "1",
            "fecha": date.today().isoformat(),
            "detalle": [{"descripcion": "Item 1", "cantidad": 1, "precio_unitario": 100}],
        },
    )
    compra_id = created.json()["id"]
    response = await client.post(
        f"/costos/compras/{compra_id}/detalle",
        json={"descripcion": "Item 2", "cantidad": 1, "precio_unitario": 50},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["subtotal"] == 150
    assert len(body["detalle"]) == 2
    assert body["saldo_pendiente"] == 150


async def test_create_compra_detalle_referencing_insumo(client):
    proveedor = await _create_proveedor(client)
    insumo = (
        await client.post(
            "/costos/insumos", json={"nombre": "Harina 000", "unidad_medida": "KG", "cantidad": 1, "precio": 1000}
        )
    ).json()

    response = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "1",
            "fecha": date.today().isoformat(),
            "detalle": [{"tipo": "INSUMO", "insumo_id": insumo["id"], "cantidad": 10, "precio_unitario": 1000}],
        },
    )
    assert response.status_code == 201
    detalle = response.json()["detalle"][0]
    assert detalle["tipo"] == "INSUMO"
    assert detalle["insumo_id"] == insumo["id"]
    assert detalle["descripcion"] == "Harina 000"


async def test_create_compra_detalle_referencing_item_gasto(client):
    proveedor = await _create_proveedor(client)
    item_gasto = (await client.post("/costos/items-gasto", json={"nombre": "Flete"})).json()

    response = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "1",
            "fecha": date.today().isoformat(),
            "detalle": [
                {"tipo": "ITEM_GASTO", "item_gasto_id": item_gasto["id"], "cantidad": 1, "precio_unitario": 5000}
            ],
        },
    )
    assert response.status_code == 201
    detalle = response.json()["detalle"][0]
    assert detalle["tipo"] == "ITEM_GASTO"
    assert detalle["item_gasto_id"] == item_gasto["id"]
    assert detalle["descripcion"] == "Flete"


async def test_create_compra_detalle_referencing_item_gasto_with_descripcion_override(client):
    proveedor = await _create_proveedor(client)
    item_gasto = (await client.post("/costos/items-gasto", json={"nombre": "Flete"})).json()

    response = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "1",
            "fecha": date.today().isoformat(),
            "detalle": [
                {
                    "tipo": "ITEM_GASTO",
                    "item_gasto_id": item_gasto["id"],
                    "descripcion": "Flete a depósito Rosario",
                    "cantidad": 1,
                    "precio_unitario": 5000,
                }
            ],
        },
    )
    assert response.status_code == 201
    assert response.json()["detalle"][0]["descripcion"] == "Flete a depósito Rosario"


async def test_reject_compra_detalle_insumo_not_found(client):
    proveedor = await _create_proveedor(client)
    response = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "1",
            "fecha": date.today().isoformat(),
            "detalle": [{"tipo": "INSUMO", "insumo_id": 999999, "cantidad": 1, "precio_unitario": 100}],
        },
    )
    assert response.status_code == 404


async def test_reject_compra_detalle_libre_without_descripcion(client):
    proveedor = await _create_proveedor(client)
    response = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "1",
            "fecha": date.today().isoformat(),
            "detalle": [{"cantidad": 1, "precio_unitario": 100}],
        },
    )
    assert response.status_code == 400


async def test_reject_compra_detalle_insumo_with_item_gasto_id(client):
    proveedor = await _create_proveedor(client)
    insumo = (
        await client.post(
            "/costos/insumos", json={"nombre": "Harina 000", "unidad_medida": "KG", "cantidad": 1, "precio": 1000}
        )
    ).json()
    response = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "1",
            "fecha": date.today().isoformat(),
            "detalle": [
                {
                    "tipo": "INSUMO",
                    "insumo_id": insumo["id"],
                    "item_gasto_id": 1,
                    "cantidad": 1,
                    "precio_unitario": 100,
                }
            ],
        },
    )
    assert response.status_code == 400


async def test_historical_migration_tipo_accepted(client):
    proveedor = await _create_proveedor(client)
    response = await client.post(
        "/costos/compras",
        json={
            "proveedor_id": proveedor["id"],
            "tipo_comprobante": "FACTURA_A",
            "numero": "1",
            "fecha": date.today().isoformat(),
            "impuestos": [{"tipo": "HISTORICO_SIN_DESGLOSE", "importe": 500}],
        },
    )
    assert response.status_code == 201
    assert response.json()["impuestos"] == 500
