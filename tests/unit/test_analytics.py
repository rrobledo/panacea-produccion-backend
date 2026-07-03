from datetime import date

from sqlalchemy import text

from app.models.insumos import Insumos
from app.models.productos import Costos, Productos


async def _make_producto(session, **overrides):
    defaults = dict(codigo="P1", nombre="Pan", utilidad=10, precio_actual=100, lote_produccion=10, habilitado=True)
    defaults.update(overrides)
    producto = Productos(**defaults)
    session.add(producto)
    await session.commit()
    await session.refresh(producto)
    return producto


async def test_produccion_by_category_aggregates_plan_prod_vendido(client, session):
    producto = await _make_producto(session, nombre="Pan", categoria="PANADERIA")

    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, prod, producto_id, fecha) "
            "VALUES ('Todos', 50, 40, :pid, :fecha)"
        ),
        {"pid": producto.id, "fecha": date(2026, 7, 10)},
    )
    await session.execute(
        text(
            "INSERT INTO costos_planificacion (fecha, producto_id, corregido) VALUES (:fecha, :pid, 100)"
        ),
        {"fecha": date(2026, 7, 1), "pid": producto.id},
    )
    await session.execute(
        text(
            "INSERT INTO panacea_sales_v2 (operation_year, operation_month, product_id, count) "
            "VALUES (2026, 7, :pid, 30)"
        ),
        {"pid": producto.id},
    )
    await session.commit()

    response = await client.get("/costos/get_produccion_by_category", params={"anio": 2026, "mes": 7})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["categoria"] == "PANADERIA"
    assert row["planeado"] == 100
    assert row["producido"] == 40
    assert row["vendido"] == 30
    assert row["porcentaje_ejecutado"] == 40.0
    assert row["porcentaje_vendido"] == 30.0


async def test_produccion_by_productos_joins_planificacion2024_by_ref_id(client, session):
    producto = await _make_producto(session, nombre="Pan Frances", categoria="PANADERIA", ref_id="7001")
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, prod, producto_id, fecha) "
            "VALUES ('Todos', 50, 40, :pid, :fecha)"
        ),
        {"pid": producto.id, "fecha": date(2026, 7, 10)},
    )
    await session.execute(
        text("INSERT INTO costos_planificacion (fecha, producto_id, corregido) VALUES (:fecha, :pid, 100)"),
        {"fecha": date(2026, 7, 1), "pid": producto.id},
    )
    await session.execute(
        text("INSERT INTO planificacion2024 (codigo, producto_id) VALUES (7001, :pid)"), {"pid": producto.id}
    )
    await session.commit()

    response = await client.get("/costos/get_produccion_by_productos", params={"anio": 2026, "mes": 7})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["producto"] == "Pan Frances"
    assert rows[0]["planeado"] == 100
    assert rows[0]["producido"] == 40


async def test_produccion_by_productos_excludes_unmapped_ref_id(client, session):
    producto = await _make_producto(session, nombre="SinRef", ref_id="9999")
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, prod, producto_id, fecha) "
            "VALUES ('Todos', 50, 40, :pid, :fecha)"
        ),
        {"pid": producto.id, "fecha": date(2026, 7, 10)},
    )
    await session.execute(
        text("INSERT INTO costos_planificacion (fecha, producto_id, corregido) VALUES (:fecha, :pid, 100)"),
        {"fecha": date(2026, 7, 1), "pid": producto.id},
    )
    await session.commit()

    response = await client.get("/costos/get_produccion_by_productos", params={"anio": 2026, "mes": 7})
    assert response.status_code == 200
    assert response.json() == []


async def test_produccion_by_category_excludes_zero_plan(client, session):
    producto = await _make_producto(session, nombre="SinPlan")
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, prod, producto_id, fecha) "
            "VALUES ('Todos', 10, 5, :pid, :fecha)"
        ),
        {"pid": producto.id, "fecha": date(2026, 7, 10)},
    )
    await session.commit()

    response = await client.get("/costos/get_produccion_by_category", params={"anio": 2026, "mes": 7})
    assert response.status_code == 200
    assert response.json() == []


async def test_insumos_by_month_weekly_and_monthly_totals(client, session):
    producto = await _make_producto(session, nombre="Pan", lote_produccion=10)
    insumo = await _make_insumo(session)
    session.add(Costos(producto_id=producto.id, insumo_id=insumo.id, cantidad=1))
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, prod, producto_id, fecha) "
            "VALUES ('Todos', 10, 8, :pid, :fecha)"
        ),
        {"pid": producto.id, "fecha": date(2026, 7, 10)},
    )
    await session.commit()

    weekly = await client.get(
        "/costos/get_insumos_by_month", params={"anio": 2026, "mes": 7, "by_week": "yes"}
    )
    assert weekly.status_code == 200
    weekly_rows = weekly.json()
    assert any(r["insumo"] == "Total" for r in weekly_rows)
    assert any(r["insumo"] == insumo.nombre for r in weekly_rows)

    monthly = await client.get(
        "/costos/get_insumos_by_month", params={"anio": 2026, "mes": 7, "by_week": "no"}
    )
    assert monthly.status_code == 200
    assert any(r["insumo"] == "Total" for r in monthly.json())


async def _make_insumo(session, **overrides):
    defaults = dict(nombre="Harina", unidad_medida="KG", cantidad=1, precio=100)
    defaults.update(overrides)
    insumo = Insumos(**defaults)
    session.add(insumo)
    await session.commit()
    await session.refresh(insumo)
    return insumo


async def test_ventas_por_cliente_filters_by_named_client(client, session):
    await session.execute(
        text(
            "INSERT INTO panacea_sales_v2 (operation_date, operation_hour, customer_id, count, subtotal, document_id) "
            "VALUES (:d, 10, 888, 5, 500, 1)"
        ),
        {"d": date(2026, 7, 3)},
    )
    await session.execute(
        text(
            "INSERT INTO panacea_sales_v2 (operation_date, operation_hour, customer_id, count, subtotal, document_id) "
            "VALUES (:d, 18, 0, 3, 300, 2)"
        ),
        {"d": date(2026, 7, 3)},
    )
    await session.commit()

    response = await client.get(
        "/costos/get_ventas_por_cliente",
        params={"anio": 2026, "mes": 7, "cliente": "Panacea Cordoba"},
    )
    assert response.status_code == 200
    # The reference SQL's filter (`cliente = :cliente`) matches the raw,
    # un-stripped column — 'TOTAL'/'SUBTOTAL' rows and the space-prefixed
    # duplicate variant never equal the exact client name, so only the
    # single unprefixed row for that client survives a named-client filter
    # (unlike the `cliente=Todos` case, which returns everything).
    rows = response.json()
    assert [row["cliente"] for row in rows] == ["Panacea Cordoba"]
    assert rows[0]["cantidad"] == 5


async def test_ventas_por_cliente_mes_zero_includes_all_months(client, session):
    await session.execute(
        text(
            "INSERT INTO panacea_sales_v2 (operation_date, operation_hour, customer_id, count, subtotal, document_id) "
            "VALUES (:d1, 10, 888, 1, 100, 1), (:d2, 10, 888, 1, 100, 2)"
        ),
        {"d1": date(2026, 1, 5), "d2": date(2026, 6, 5)},
    )
    await session.commit()

    response = await client.get("/costos/get_ventas_por_cliente", params={"anio": 2026, "mes": 0})
    assert response.status_code == 200
    week_labels = {row["week_of_month"] for row in response.json()}
    assert any(label.startswith("2026-01") for label in week_labels)
    assert any(label.startswith("2026-06") for label in week_labels)


async def test_sql_injection_attempt_in_cliente_param_is_inert(client, session):
    response = await client.get(
        "/costos/get_ventas_por_cliente",
        params={"anio": 2026, "mes": 7, "cliente": "x' OR '1'='1"},
    )
    assert response.status_code == 200
    assert response.json() == []
