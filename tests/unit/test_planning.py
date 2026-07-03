from datetime import date

import pytest
from sqlalchemy import text

from app.models.productos import Productos


async def _make_producto(session, **overrides):
    defaults = dict(codigo="P1", nombre="Pan", utilidad=10, precio_actual=100, lote_produccion=10, habilitado=True)
    defaults.update(overrides)
    producto = Productos(**defaults)
    session.add(producto)
    await session.commit()
    await session.refresh(producto)
    return producto


async def test_generate_planning_zero_fill_for_product_with_no_prior_sales(client, session):
    producto = await _make_producto(session, nombre="Sin Ventas")

    response = await client.post(
        "/costos/planning/generate",
        params={"year": 2026, "producto_id": producto.id, "dry_run": "false"},
    )
    assert response.status_code == 200
    assert response.json()["rows_inserted"] == 12

    rows = (
        await session.execute(
            text("SELECT plan, sistema, indice FROM costos_planificacion WHERE producto_id = :pid"),
            {"pid": producto.id},
        )
    ).all()
    assert len(rows) == 12
    assert all(r.plan == 0 and r.sistema == 0 and r.indice == 0 for r in rows)


async def test_generate_planning_sales_projection_matches_hand_computed_values(client, session):
    producto = await _make_producto(session, nombre="Con Ventas")
    # 2 lugares, 2 months of 2025 sales data (year - 1 for a 2026 generation).
    # lugar 1: month1=100, month2=200 (avg=150); lugar 2: month1=50, month2=50 (avg=50)
    for mes, lugar, count in [(1, 1, 100), (2, 1, 200), (1, 2, 50), (2, 2, 50)]:
        await session.execute(
            text(
                "INSERT INTO panacea_sales_v2 (product_id, operation_year, operation_month, lugar_venta_id, count) "
                "VALUES (:pid, 2025, :mes, :lugar, :count)"
            ),
            {"pid": producto.id, "mes": mes, "lugar": lugar, "count": count},
        )
    await session.commit()

    response = await client.post(
        "/costos/planning/generate",
        params={"year": 2026, "producto_id": producto.id, "dry_run": "false"},
    )
    assert response.status_code == 200
    assert response.json()["rows_inserted"] == 12

    rows = {
        r.fecha.month: r
        for r in (
            await session.execute(
                text("SELECT fecha, plan, sistema, indice FROM costos_planificacion WHERE producto_id = :pid"),
                {"pid": producto.id},
            )
        ).all()
    }

    # promedio_venta = round(((100+50) + (200+50)) / 2) = round(200) = 200
    # month1: indice = avg(100/150, 50/50) = avg(0.6667, 1.0) = 0.8333
    #   plan = ceil(200 * 0.8333 / 10) * 10 = ceil(16.667) * 10 = 170
    assert rows[1].plan == 170
    assert rows[1].sistema == 170
    assert rows[1].indice == pytest.approx(0.83, abs=0.01)

    # month2: indice = avg(200/150, 50/50) = avg(1.3333, 1.0) = 1.16665
    #   plan = ceil(200 * 1.16665 / 10) * 10 = ceil(23.333) * 10 = 240
    assert rows[2].plan == 240
    assert rows[2].sistema == 240

    # months 3-12 have no 2025 sales data -> zero-fill, still exactly 12 rows total
    for month in range(3, 13):
        assert rows[month].plan == 0
        assert rows[month].sistema == 0
        assert rows[month].indice == 0


async def test_generate_planning_dry_run_does_not_write(client, session):
    producto = await _make_producto(session)

    response = await client.post(
        "/costos/planning/generate", params={"year": 2026, "producto_id": producto.id, "dry_run": "true"}
    )
    assert response.status_code == 200
    assert response.json()["count"] == 12

    count = (
        await session.execute(
            text("SELECT count(*) FROM costos_planificacion WHERE producto_id = :pid"), {"pid": producto.id}
        )
    ).scalar_one()
    assert count == 0


async def test_scoped_generation_matches_equivalent_slice_of_bulk_run(client, session):
    target = await _make_producto(session, nombre="Target")
    other = await _make_producto(session, nombre="Other")
    for producto in (target, other):
        await session.execute(
            text(
                "INSERT INTO panacea_sales_v2 (product_id, operation_year, operation_month, lugar_venta_id, count) "
                "VALUES (:pid, 2025, 3, 1, 90)"
            ),
            {"pid": producto.id},
        )
    await session.commit()

    scoped = await client.post(
        "/costos/planning/generate", params={"year": 2026, "producto_id": target.id, "dry_run": "false"}
    )
    assert scoped.json()["rows_inserted"] == 12

    bulk = await client.post("/costos/planning/generate", params={"year": 2026, "dry_run": "false"})
    # Only `other` is new — `target`'s 12 rows already exist from the scoped call.
    assert bulk.json()["rows_inserted"] == 12

    target_row = (
        await session.execute(
            text(
                "SELECT plan, indice FROM costos_planificacion WHERE producto_id = :pid AND extract(month from fecha) = 3"
            ),
            {"pid": target.id},
        )
    ).one()
    other_row = (
        await session.execute(
            text(
                "SELECT plan, indice FROM costos_planificacion WHERE producto_id = :pid AND extract(month from fecha) = 3"
            ),
            {"pid": other.id},
        )
    ).one()
    assert target_row.plan == other_row.plan
    assert target_row.indice == other_row.indice


async def test_generate_planning_is_idempotent(client, session):
    producto = await _make_producto(session)

    first = await client.post(
        "/costos/planning/generate", params={"year": 2026, "producto_id": producto.id, "dry_run": "false"}
    )
    assert first.json()["rows_inserted"] == 12

    second = await client.post(
        "/costos/planning/generate", params={"year": 2026, "producto_id": producto.id, "dry_run": "false"}
    )
    assert second.json()["rows_inserted"] == 0


async def test_generate_planning_rejects_disabled_producto_id_scope(client, session):
    producto = await _make_producto(session, habilitado=False)

    response = await client.post(
        "/costos/planning/generate", params={"year": 2026, "producto_id": producto.id, "dry_run": "true"}
    )
    assert response.status_code == 400


async def test_generate_planning_rejects_out_of_range_year(client, session):
    producto = await _make_producto(session)
    response = await client.post(
        "/costos/planning/generate", params={"year": 1500, "producto_id": producto.id, "dry_run": "true"}
    )
    assert response.status_code == 400


async def test_get_planning_pivots_rows_and_includes_total(client, session):
    producto = await _make_producto(session, nombre="Pan", prioridad=1)
    await session.execute(
        text(
            "INSERT INTO costos_planificacion (fecha, producto_id, plan, sistema, corregido) "
            "VALUES (:fecha, :pid, 100, 90, 95)"
        ),
        {"fecha": date(2026, 7, 1), "pid": producto.id},
    )
    await session.commit()

    response = await client.get("/costos/planning", params={"anio": 2026})
    assert response.status_code == 200
    rows = response.json()
    producto_row = next(r for r in rows if r["id"] == producto.id)
    assert producto_row["202607-PLAN"] == 100
    assert producto_row["202607-CORREGIDO"] == 95
    total_row = next(r for r in rows if r["id"] == 999)
    assert total_row["producto_nombre"] == "TOTAL"
    assert total_row["202607-PLAN"] == 100


async def test_post_planning_updates_only_specified_field(client, session):
    producto = await _make_producto(session)
    await session.execute(
        text(
            "INSERT INTO costos_planificacion (fecha, producto_id, plan, sistema, corregido) "
            "VALUES (:fecha, :pid, 100, 90, 80)"
        ),
        {"fecha": date(2026, 7, 1), "pid": producto.id},
    )
    await session.commit()

    response = await client.post(
        "/costos/planning", json=[{"id": producto.id, "202607-CORREGIDO": 150}]
    )
    assert response.status_code == 204

    row = (
        await session.execute(
            text("SELECT plan, sistema, corregido FROM costos_planificacion WHERE producto_id = :pid"),
            {"pid": producto.id},
        )
    ).one()
    assert row.corregido == 150
    assert row.plan == 100
    assert row.sistema == 90


async def test_planning_columnas_returns_one_group_per_month(client, session):
    producto = await _make_producto(session)
    for month in (1, 2):
        await session.execute(
            text("INSERT INTO costos_planificacion (fecha, producto_id, plan) VALUES (:fecha, :pid, 10)"),
            {"fecha": date(2026, month, 1), "pid": producto.id},
        )
    await session.commit()

    response = await client.get("/costos/planning_columnas", params={"anio": 2026})
    assert response.status_code == 200
    body = response.json()
    year_group = next(g for g in body if g["headerName"] == "Anio 2026")
    assert len(year_group["children"]) == 2
    assert year_group["children"][0]["headerName"] == "Enero"
