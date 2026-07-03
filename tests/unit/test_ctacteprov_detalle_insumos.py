from datetime import date

from app.models.insumos import Insumos


async def _make_proveedor(client, cuit="50-1-1"):
    response = await client.post("/costos/proveedores", json={"nombre": "Proveedor Detalle", "cuit": cuit})
    return response.json()

async def _make_insumo(session, nombre="Harina"):
    insumo = Insumos(nombre=nombre, unidad_medida="KG", cantidad=1, precio=100)
    session.add(insumo)
    await session.commit()
    await session.refresh(insumo)
    return insumo


async def test_iva_and_percepcion_persist_and_default_to_zero(client):
    proveedor = await _make_proveedor(client)

    with_values = await client.post(
        "/costos/ctacteprov",
        json={
            "proveedor": proveedor["id"],
            "numero": "1",
            "fecha_emision": date.today().isoformat(),
            "importe_total": 1210,
            "iva": 210,
            "percepcion": 30,
        },
    )
    assert with_values.status_code == 201
    assert with_values.json()["iva"] == 210
    assert with_values.json()["percepcion"] == 30

    without_values = await client.post(
        "/costos/ctacteprov",
        json={
            "proveedor": proveedor["id"],
            "numero": "2",
            "fecha_emision": date.today().isoformat(),
            "importe_total": 500,
        },
    )
    assert without_values.status_code == 201
    assert without_values.json()["iva"] == 0
    assert without_values.json()["percepcion"] == 0


async def test_create_with_nested_insumos_creates_detail_rows(client, session):
    proveedor = await _make_proveedor(client)
    insumo = await _make_insumo(session)

    response = await client.post(
        "/costos/ctacteprov",
        json={
            "proveedor": proveedor["id"],
            "numero": "3",
            "fecha_emision": date.today().isoformat(),
            "importe_total": 500,
            "insumos": [{"insumo": insumo.id, "cantidad": 10, "subtotal": 500}],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["insumos"] == [{"id": body["insumos"][0]["id"], "insumo": insumo.id, "cantidad": 10, "subtotal": 500}]


async def test_get_one_includes_insumos_array(client, session):
    proveedor = await _make_proveedor(client)
    insumo = await _make_insumo(session)
    created = (
        await client.post(
            "/costos/ctacteprov",
            json={
                "proveedor": proveedor["id"],
                "numero": "4",
                "fecha_emision": date.today().isoformat(),
                "importe_total": 100,
                "insumos": [{"insumo": insumo.id, "cantidad": 1, "subtotal": 100}],
            },
        )
    ).json()

    fetched = await client.get(f"/costos/ctacteprov/{created['id']}")
    assert fetched.status_code == 200
    assert len(fetched.json()["insumos"]) == 1
    assert fetched.json()["insumos"][0]["insumo"] == insumo.id


async def test_list_insumos_returns_only_rows_for_that_entry(client, session):
    proveedor = await _make_proveedor(client)
    insumo = await _make_insumo(session)
    entry_a = (
        await client.post(
            "/costos/ctacteprov",
            json={
                "proveedor": proveedor["id"],
                "numero": "5",
                "fecha_emision": date.today().isoformat(),
                "importe_total": 100,
                "insumos": [{"insumo": insumo.id, "cantidad": 1, "subtotal": 100}],
            },
        )
    ).json()
    entry_b = (
        await client.post(
            "/costos/ctacteprov",
            json={
                "proveedor": proveedor["id"],
                "numero": "6",
                "fecha_emision": date.today().isoformat(),
                "importe_total": 200,
                "insumos": [{"insumo": insumo.id, "cantidad": 2, "subtotal": 200}],
            },
        )
    ).json()

    listed = await client.get(f"/costos/ctacteprov/{entry_a['id']}/insumos")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["subtotal"] == 100

    unknown = await client.get("/costos/ctacteprov/999999/insumos")
    assert unknown.status_code == 404


async def test_post_insumos_accepts_single_object_and_array(client, session):
    proveedor = await _make_proveedor(client)
    insumo = await _make_insumo(session)
    entry = (
        await client.post(
            "/costos/ctacteprov",
            json={
                "proveedor": proveedor["id"],
                "numero": "7",
                "fecha_emision": date.today().isoformat(),
                "importe_total": 0,
            },
        )
    ).json()

    single = await client.post(
        f"/costos/ctacteprov/{entry['id']}/insumos",
        json={"insumo": insumo.id, "cantidad": 1, "subtotal": 10},
    )
    assert single.status_code == 201
    assert len(single.json()) == 1

    batch = await client.post(
        f"/costos/ctacteprov/{entry['id']}/insumos",
        json=[
            {"insumo": insumo.id, "cantidad": 2, "subtotal": 20},
            {"insumo": insumo.id, "cantidad": 3, "subtotal": 30},
        ],
    )
    assert batch.status_code == 201
    assert len(batch.json()) == 2

    listed = await client.get(f"/costos/ctacteprov/{entry['id']}/insumos")
    assert len(listed.json()) == 3

    unknown_entry = await client.post(
        "/costos/ctacteprov/999999/insumos", json={"insumo": insumo.id, "cantidad": 1, "subtotal": 1}
    )
    assert unknown_entry.status_code == 404


async def test_delete_insumo_detalle_removes_only_target_row(client, session):
    proveedor = await _make_proveedor(client)
    insumo = await _make_insumo(session)
    entry_a = (
        await client.post(
            "/costos/ctacteprov",
            json={
                "proveedor": proveedor["id"],
                "numero": "8",
                "fecha_emision": date.today().isoformat(),
                "importe_total": 0,
                "insumos": [
                    {"insumo": insumo.id, "cantidad": 1, "subtotal": 10},
                    {"insumo": insumo.id, "cantidad": 2, "subtotal": 20},
                ],
            },
        )
    ).json()
    entry_b = (
        await client.post(
            "/costos/ctacteprov",
            json={
                "proveedor": proveedor["id"],
                "numero": "9",
                "fecha_emision": date.today().isoformat(),
                "importe_total": 0,
                "insumos": [{"insumo": insumo.id, "cantidad": 1, "subtotal": 5}],
            },
        )
    ).json()

    detalle_ids_a = [d["id"] for d in entry_a["insumos"]]
    detalle_id_b = entry_b["insumos"][0]["id"]

    deleted = await client.delete(f"/costos/ctacteprov/{entry_a['id']}/insumos/{detalle_ids_a[0]}")
    assert deleted.status_code == 204

    remaining = (await client.get(f"/costos/ctacteprov/{entry_a['id']}/insumos")).json()
    assert [r["id"] for r in remaining] == [detalle_ids_a[1]]

    mismatched = await client.delete(f"/costos/ctacteprov/{entry_a['id']}/insumos/{detalle_id_b}")
    assert mismatched.status_code == 404


async def test_deleting_entry_cascades_to_delete_detalle_rows(client, session):
    proveedor = await _make_proveedor(client)
    insumo = await _make_insumo(session)
    entry = (
        await client.post(
            "/costos/ctacteprov",
            json={
                "proveedor": proveedor["id"],
                "numero": "10",
                "fecha_emision": date.today().isoformat(),
                "importe_total": 0,
                "insumos": [
                    {"insumo": insumo.id, "cantidad": 1, "subtotal": 10},
                    {"insumo": insumo.id, "cantidad": 2, "subtotal": 20},
                    {"insumo": insumo.id, "cantidad": 3, "subtotal": 30},
                ],
            },
        )
    ).json()

    deleted = await client.delete(f"/costos/ctacteprov/{entry['id']}")
    assert deleted.status_code == 204

    from sqlalchemy import select

    from app.models.cuenta_corriente import CuentaCorrienteProveedorDetalle

    result = await session.execute(
        select(CuentaCorrienteProveedorDetalle).where(
            CuentaCorrienteProveedorDetalle.cuentacorrienteproveedor_id == entry["id"]
        )
    )
    assert result.scalars().all() == []
