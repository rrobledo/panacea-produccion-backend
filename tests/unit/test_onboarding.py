from sqlalchemy import text


async def _create_producto(client, nombre, prioridad=10):
    response = await client.post(
        "/costos/productos",
        json={
            "codigo": nombre,
            "nombre": nombre,
            "utilidad": 20,
            "precio_actual": 100,
            "lote_produccion": 10,
            "tiempo_produccion": 1,
            "prioridad": prioridad,
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_onboarding_scoped_generation_matches_bulk_for_the_same_product(client, session):
    # Two products with identical prior-year sales data: `onboarded` is
    # generated via the documented onboarding call sequence (scoped to its
    # own id, immediately after creation); `bulk_baseline` is generated via
    # the plain bulk (no producto_id) calls. Per design.md D8, the two
    # should produce identical rows for their respective product.
    onboarded = await _create_producto(client, "Onboarded Product")
    bulk_baseline = await _create_producto(client, "Bulk Baseline Product")

    for producto in (onboarded, bulk_baseline):
        await session.execute(
            text(
                "INSERT INTO panacea_sales_v2 (product_id, operation_year, operation_month, lugar_venta_id, count) "
                "VALUES (:pid, 2025, 3, 1, 90)"
            ),
            {"pid": producto["id"]},
        )
    await session.commit()

    # --- Onboarding sequence for `onboarded`, scoped to its own id ---
    planning = await client.post(
        "/costos/planning/generate",
        params={"year": 2026, "producto_id": onboarded["id"], "dry_run": "false"},
    )
    assert planning.status_code == 200
    assert planning.json()["rows_inserted"] == 12

    programacion = await client.post(
        "/costos/programacion/generate",
        params={"year": 2026, "month": 3, "producto_id": onboarded["id"], "dry_run": "false"},
    )
    assert programacion.status_code == 200
    assert programacion.json()["day_rows_inserted"] > 0

    # --- Bulk generation covers `bulk_baseline` (and, redundantly, the
    # already-onboarded product — which is a no-op there due to idempotency) ---
    bulk_planning = await client.post("/costos/planning/generate", params={"year": 2026, "dry_run": "false"})
    assert bulk_planning.status_code == 200

    bulk_programacion = await client.post(
        "/costos/programacion/generate", params={"year": 2026, "month": 3, "dry_run": "false"}
    )
    assert bulk_programacion.status_code == 200

    # --- Compare: onboarded product's rows match the bulk-generated
    # baseline product's rows exactly (same sales fixture -> same formula
    # inputs -> same plan/indice and same set of programacion dates) ---
    onboarded_planning = (
        await session.execute(
            text(
                "SELECT extract(month from fecha) as mes, plan, indice FROM costos_planificacion "
                "WHERE producto_id = :pid ORDER BY mes"
            ),
            {"pid": onboarded["id"]},
        )
    ).all()
    baseline_planning = (
        await session.execute(
            text(
                "SELECT extract(month from fecha) as mes, plan, indice FROM costos_planificacion "
                "WHERE producto_id = :pid ORDER BY mes"
            ),
            {"pid": bulk_baseline["id"]},
        )
    ).all()
    assert [(r.mes, r.plan, r.indice) for r in onboarded_planning] == [
        (r.mes, r.plan, r.indice) for r in baseline_planning
    ]

    onboarded_days = (
        await session.execute(
            text("SELECT fecha FROM costos_programacion WHERE producto_id = :pid ORDER BY fecha"),
            {"pid": onboarded["id"]},
        )
    ).scalars().all()
    baseline_days = (
        await session.execute(
            text("SELECT fecha FROM costos_programacion WHERE producto_id = :pid ORDER BY fecha"),
            {"pid": bulk_baseline["id"]},
        )
    ).scalars().all()
    assert onboarded_days == baseline_days
