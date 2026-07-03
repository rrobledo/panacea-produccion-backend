from datetime import date

from sqlalchemy import text

from app.models.productos import Productos


async def _make_producto(session, **overrides):
    defaults = dict(codigo="P1", nombre="Pan", utilidad=10, precio_actual=100, lote_produccion=10, habilitado=True, is_producto=True)
    defaults.update(overrides)
    producto = Productos(**defaults)
    session.add(producto)
    await session.commit()
    await session.refresh(producto)
    return producto


async def _enroll_in_planning(session, producto_id, year=2026, month=7):
    await session.execute(
        text(
            "INSERT INTO costos_planificacion (fecha, producto_id, plan, sistema, corregido) "
            "VALUES (:fecha, :pid, 0, 0, 0)"
        ),
        {"fecha": date(year, month, 1), "pid": producto_id},
    )
    await session.commit()


async def test_generate_programacion_inserts_business_days_for_eligible_product(client, session):
    producto = await _make_producto(session)
    await _enroll_in_planning(session, producto.id)

    response = await client.post(
        "/costos/programacion/generate",
        params={"year": 2026, "month": 7, "producto_id": producto.id, "dry_run": "false"},
    )
    assert response.status_code == 200
    body = response.json()
    # July 2026 has 31 days, 5 Sundays (5,12,19,26 + none else - actually
    # check: July 1 2026 is a Wednesday, so Sundays are 5,12,19,26 -> 4 Sundays).
    assert body["day_rows_inserted"] == 27

    rows = (
        await session.execute(
            text("SELECT fecha FROM costos_programacion WHERE producto_id = :pid"), {"pid": producto.id}
        )
    ).all()
    assert all(r.fecha.weekday() != 6 for r in rows)  # Python Sunday=6


async def test_generate_programacion_bulk_covers_all_eligible_and_skips_disabled(client, session):
    eligible = await _make_producto(session, nombre="Eligible")
    await _enroll_in_planning(session, eligible.id)
    disabled = await _make_producto(session, nombre="Disabled", habilitado=False)
    await _enroll_in_planning(session, disabled.id)

    response = await client.post(
        "/costos/programacion/generate", params={"year": 2026, "month": 7, "dry_run": "false"}
    )
    assert response.status_code == 200
    assert response.json()["day_rows_inserted"] > 0

    eligible_rows = (
        await session.execute(
            text("SELECT count(*) FROM costos_programacion WHERE producto_id = :pid"), {"pid": eligible.id}
        )
    ).scalar_one()
    disabled_rows = (
        await session.execute(
            text("SELECT count(*) FROM costos_programacion WHERE producto_id = :pid"), {"pid": disabled.id}
        )
    ).scalar_one()
    assert eligible_rows > 0
    assert disabled_rows == 0


async def test_programacion_columnas_groups_business_days_into_weeks(client, session):
    producto = await _make_producto(session)
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, producto_id, fecha) VALUES ('Todos', :pid, :fecha)"
        ),
        {"pid": producto.id, "fecha": date(2026, 7, 15)},
    )
    await session.commit()

    response = await client.get("/costos/programacion_columnas", params={"anio": 2026, "mes": 7})
    assert response.status_code == 200
    body = response.json()
    week_groups = [g for g in body if g["headerName"].startswith("Semana")]
    assert len(week_groups) >= 1
    assert any("20260715-P" in c["field"] for g in week_groups for c in g["children"][0]["children"])


async def test_generate_programacion_rejects_ineligible_producto_id(client, session):
    producto = await _make_producto(session)
    # Not enrolled in planning at all.
    response = await client.post(
        "/costos/programacion/generate",
        params={"year": 2026, "month": 7, "producto_id": producto.id, "dry_run": "true"},
    )
    assert response.status_code == 400


async def test_generate_programacion_is_idempotent(client, session):
    producto = await _make_producto(session)
    await _enroll_in_planning(session, producto.id)

    first = await client.post(
        "/costos/programacion/generate",
        params={"year": 2026, "month": 7, "producto_id": producto.id, "dry_run": "false"},
    )
    second = await client.post(
        "/costos/programacion/generate",
        params={"year": 2026, "month": 7, "producto_id": producto.id, "dry_run": "false"},
    )
    assert first.json()["day_rows_inserted"] > 0
    assert second.json()["day_rows_inserted"] == 0


async def test_generate_programacion_dry_run_does_not_write(client, session):
    producto = await _make_producto(session)
    await _enroll_in_planning(session, producto.id)

    response = await client.post(
        "/costos/programacion/generate",
        params={"year": 2026, "month": 7, "producto_id": producto.id, "dry_run": "true"},
    )
    assert response.status_code == 200
    assert len(response.json()["day_rows_that_would_be_inserted"]) > 0

    count = (
        await session.execute(
            text("SELECT count(*) FROM costos_programacion WHERE producto_id = :pid"), {"pid": producto.id}
        )
    ).scalar_one()
    assert count == 0


async def _setup_correction_fixture(session, producto_id, prev_plan, prev_corr, prev_venta):
    await session.execute(
        text(
            "INSERT INTO costos_planificacion (fecha, producto_id, plan, sistema, corregido) "
            "VALUES (:fecha, :pid, :plan, 0, :corr)"
        ),
        {"fecha": date(2026, 6, 1), "pid": producto_id, "plan": prev_plan, "corr": prev_corr},
    )
    await session.execute(
        text(
            "INSERT INTO costos_planificacion (fecha, producto_id, plan, sistema, corregido) "
            "VALUES (:fecha, :pid, null, 0, 0)"
        ),
        {"fecha": date(2026, 7, 1), "pid": producto_id},
    )
    if prev_venta is not None:
        await session.execute(
            text(
                "INSERT INTO panacea_sales_v2 (product_id, operation_year, operation_month, count) "
                "VALUES (:pid, 2026, 6, :venta)"
            ),
            {"pid": producto_id, "venta": prev_venta},
        )
    await session.commit()


async def _get_current_month_planificacion(session, producto_id):
    return (
        await session.execute(
            text(
                "SELECT corregido, sistema FROM costos_planificacion "
                "WHERE producto_id = :pid AND fecha = :fecha"
            ),
            {"pid": producto_id, "fecha": date(2026, 7, 1)},
        )
    ).one()


async def test_correction_zero_guard_when_prev_venta_is_zero(client, session):
    producto = await _make_producto(session)
    await _setup_correction_fixture(session, producto.id, prev_plan=100, prev_corr=100, prev_venta=0)

    response = await client.post(
        "/costos/programacion/generate",
        params={
            "year": 2026, "month": 7, "prev_year": 2026, "prev_month": 6,
            "producto_id": producto.id, "dry_run": "false",
        },
    )
    assert response.status_code == 200
    row = await _get_current_month_planificacion(session, producto.id)
    assert row.corregido == 0


async def test_correction_branch_high_performing(client, session):
    producto = await _make_producto(session)
    await _setup_correction_fixture(session, producto.id, prev_plan=100, prev_corr=80, prev_venta=90)

    response = await client.post(
        "/costos/programacion/generate",
        params={
            "year": 2026, "month": 7, "prev_year": 2026, "prev_month": 6,
            "producto_id": producto.id, "dry_run": "false",
        },
    )
    assert response.status_code == 200
    # ratio = 90/80 = 1.125 > 0.75, prev_venta(90) >= prev_corr(80)
    # this_plan is None -> base_plan = prev_venta = 90; denom = prev_plan = 100
    # scale = 0.9; corregido = int(0.9 * 90) = 81
    row = await _get_current_month_planificacion(session, producto.id)
    assert row.corregido == 81
    assert row.sistema == 81  # sistema overwritten by the correction


async def test_correction_branch_prev_venta_below_prev_corr(client, session):
    producto = await _make_producto(session)
    await _setup_correction_fixture(session, producto.id, prev_plan=100, prev_corr=120, prev_venta=100)

    response = await client.post(
        "/costos/programacion/generate",
        params={
            "year": 2026, "month": 7, "prev_year": 2026, "prev_month": 6,
            "producto_id": producto.id, "dry_run": "false",
        },
    )
    assert response.status_code == 200
    # ratio = 100/120 = 0.8333 > 0.75, prev_venta(100) < prev_corr(120)
    # scale = prev_venta/prev_plan = 100/100 = 1.0; corregido = int(1.0 * 120) = 120
    row = await _get_current_month_planificacion(session, producto.id)
    assert row.corregido == 120


async def test_correction_branch_under_target(client, session):
    producto = await _make_producto(session)
    await _setup_correction_fixture(session, producto.id, prev_plan=100, prev_corr=200, prev_venta=100)

    response = await client.post(
        "/costos/programacion/generate",
        params={
            "year": 2026, "month": 7, "prev_year": 2026, "prev_month": 6,
            "producto_id": producto.id, "dry_run": "false",
        },
    )
    assert response.status_code == 200
    # ratio = 100/200 = 0.5 <= 0.75
    # scale = 100/100 = 1.0; corregido = int(1.0*100 + (200-100)/2) = int(150) = 150
    row = await _get_current_month_planificacion(session, producto.id)
    assert row.corregido == 150


async def test_correction_zero_guard_when_prev_corr_missing(client, session):
    producto = await _make_producto(session)
    await _setup_correction_fixture(session, producto.id, prev_plan=100, prev_corr=None, prev_venta=100)

    response = await client.post(
        "/costos/programacion/generate",
        params={
            "year": 2026, "month": 7, "prev_year": 2026, "prev_month": 6,
            "producto_id": producto.id, "dry_run": "false",
        },
    )
    assert response.status_code == 200
    row = await _get_current_month_planificacion(session, producto.id)
    assert row.corregido == 0


async def test_correction_noop_when_no_current_month_row(client, session):
    producto = await _make_producto(session)
    # Only a prev-month row exists — no row for the target (year, month).
    await session.execute(
        text(
            "INSERT INTO costos_planificacion (fecha, producto_id, plan, sistema, corregido) "
            "VALUES (:fecha, :pid, 100, 0, 100)"
        ),
        {"fecha": date(2026, 6, 1), "pid": producto.id},
    )
    await session.execute(
        text("INSERT INTO panacea_sales_v2 (product_id, operation_year, operation_month, count) VALUES (:pid, 2026, 6, 100)"),
        {"pid": producto.id},
    )
    await session.commit()

    response = await client.post(
        "/costos/programacion/generate",
        params={
            "year": 2026, "month": 7, "prev_year": 2026, "prev_month": 6,
            "producto_id": producto.id, "dry_run": "false",
        },
    )
    assert response.status_code == 200
    assert response.json()["corrections_applied"] == 0


async def test_copy_week_copies_matched_and_skips_unmatched(client, session):
    producto_a = await _make_producto(session, nombre="A")
    producto_b = await _make_producto(session, nombre="B")

    # Source week: 2026-06-22 (Mon) is ISO week 26 of 2026.
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, producto_id, fecha) "
            "VALUES ('Todos', 50, :pid, :fecha)"
        ),
        {"pid": producto_a.id, "fecha": date(2026, 6, 22)},  # Monday, week 26
    )
    # Target week: 2026-06-29 (Mon) is ISO week 27 of 2026.
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, producto_id, fecha) "
            "VALUES ('Todos', 0, :pid, :fecha)"
        ),
        {"pid": producto_a.id, "fecha": date(2026, 6, 29)},  # Monday, week 27
    )
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, producto_id, fecha) "
            "VALUES ('Todos', 5, :pid, :fecha)"
        ),
        {"pid": producto_b.id, "fecha": date(2026, 6, 29)},  # no source-week match for B
    )
    await session.commit()

    response = await client.post(
        "/costos/programacion/copy-week",
        params={"from_year": 2026, "from_week": 26, "to_year": 2026, "to_week": 27, "dry_run": "false"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 1
    assert body["skipped_no_source_match"] == 1

    a_plan = (
        await session.execute(
            text("SELECT plan FROM costos_programacion WHERE producto_id = :pid AND fecha = :fecha"),
            {"pid": producto_a.id, "fecha": date(2026, 6, 29)},
        )
    ).scalar_one()
    assert a_plan == 50

    b_plan = (
        await session.execute(
            text("SELECT plan FROM costos_programacion WHERE producto_id = :pid AND fecha = :fecha"),
            {"pid": producto_b.id, "fecha": date(2026, 6, 29)},
        )
    ).scalar_one()
    assert b_plan == 5  # left untouched, not nulled out


async def test_copy_week_handles_iso_year_boundary(client, session):
    # Risk R5: Dec 31, 2025 is a Wednesday whose ISO week/year is
    # (2026, week 1) — not (2025, week ~53) — since ISO 8601 assigns a
    # week to whichever year contains that week's Thursday. Source week
    # "2026 week 1" therefore includes a December-2025 calendar date.
    producto = await _make_producto(session)
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, producto_id, fecha) VALUES ('Todos', 77, :pid, :fecha)"
        ),
        {"pid": producto.id, "fecha": date(2025, 12, 31)},  # Wed, ISO (2026, week 1)
    )
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, producto_id, fecha) VALUES ('Todos', 0, :pid, :fecha)"
        ),
        {"pid": producto.id, "fecha": date(2026, 1, 7)},  # Wed, ISO (2026, week 2)
    )
    await session.commit()

    response = await client.post(
        "/costos/programacion/copy-week",
        params={"from_year": 2026, "from_week": 1, "to_year": 2026, "to_week": 2, "dry_run": "false"},
    )
    assert response.status_code == 200
    assert response.json()["updated"] == 1

    plan = (
        await session.execute(
            text("SELECT plan FROM costos_programacion WHERE producto_id = :pid AND fecha = :fecha"),
            {"pid": producto.id, "fecha": date(2026, 1, 7)},
        )
    ).scalar_one()
    assert plan == 77


async def test_copy_week_rejects_same_source_and_target(client, session):
    response = await client.post(
        "/costos/programacion/copy-week",
        params={"from_year": 2026, "from_week": 26, "to_year": 2026, "to_week": 26, "dry_run": "true"},
    )
    assert response.status_code == 400


async def test_copy_week_dry_run_does_not_write(client, session):
    producto = await _make_producto(session)
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, producto_id, fecha) VALUES ('Todos', 50, :pid, :fecha)"
        ),
        {"pid": producto.id, "fecha": date(2026, 6, 22)},
    )
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, producto_id, fecha) VALUES ('Todos', 0, :pid, :fecha)"
        ),
        {"pid": producto.id, "fecha": date(2026, 6, 29)},
    )
    await session.commit()

    response = await client.post(
        "/costos/programacion/copy-week",
        params={"from_year": 2026, "from_week": 26, "to_year": 2026, "to_week": 27, "dry_run": "true"},
    )
    assert response.status_code == 200
    assert len(response.json()["updates_that_would_apply"]) == 1

    unchanged = (
        await session.execute(
            text("SELECT plan FROM costos_programacion WHERE producto_id = :pid AND fecha = :fecha"),
            {"pid": producto.id, "fecha": date(2026, 6, 29)},
        )
    ).scalar_one()
    assert unchanged == 0


async def test_get_programacion_pivots_and_filters_by_responsable(client, session):
    producto = await _make_producto(session, nombre="Pan", responsable="Panaderia", prioridad=1)
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, prod, producto_id, fecha) "
            "VALUES ('Panaderia', 10, 8, :pid, :fecha)"
        ),
        {"pid": producto.id, "fecha": date(2026, 7, 15)},
    )
    await session.commit()

    response = await client.get("/costos/programacion", params={"anio": 2026, "mes": 7, "responsable": "Panaderia"})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["20260715-P"] == 10
    assert rows[0]["20260715-E"] == 8

    other = await client.get("/costos/programacion", params={"anio": 2026, "mes": 7, "responsable": "OtroEquipo"})
    assert other.json() == []


async def test_post_programacion_updates_day_field_and_responsable(client, session):
    producto = await _make_producto(session, responsable="Todos")
    await session.execute(
        text(
            "INSERT INTO costos_programacion (responsable, plan, producto_id, fecha) VALUES ('Todos', 0, :pid, :fecha)"
        ),
        {"pid": producto.id, "fecha": date(2026, 7, 15)},
    )
    await session.commit()

    response = await client.post(
        "/costos/programacion",
        json=[{"id": producto.id, "responsable": "Nuevo", "20260715-P": 80}],
    )
    assert response.status_code == 204

    plan = (
        await session.execute(
            text("SELECT plan FROM costos_programacion WHERE producto_id = :pid"), {"pid": producto.id}
        )
    ).scalar_one()
    assert plan == 80
    responsable = (
        await session.execute(text("SELECT responsable FROM costos_productos WHERE id = :pid"), {"pid": producto.id})
    ).scalar_one()
    assert responsable == "Nuevo"


async def test_cron_endpoint_requires_cron_secret(client, session):
    from app.deps import require_cron_secret
    from app.main import app

    app.dependency_overrides.pop(require_cron_secret, None)
    response = await client.post("/internal/cron/monthly-cascade")
    assert response.status_code == 401
