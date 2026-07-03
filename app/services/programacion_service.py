import calendar
import itertools
from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.planificacion import Planificacion
from app.models.productos import Productos
from app.models.programacion import Programacion


def _relative_week_case(mes: int) -> str:
    # Ported verbatim from the reference (produccion.py::get_programacion /
    # get_programacion_columns): the "week within month" baseline is a
    # hardcoded '2024-{mes}-02', not tied to the queried `anio`. Preserved
    # as-is for parity — changing it without being asked risks diverging
    # from behavior the frontend may already depend on.
    return (
        f"case when extract('week' from fecha) - extract('week' from '2024-{mes:02d}-02'::date) + 1 < 0 then 5 "
        f"else extract('week' from fecha) - extract('week' from '2024-{mes:02d}-02'::date) + 1 end"
    )


async def get_programacion(
    session: AsyncSession, anio: int, mes: int, responsable: str | None, semana: int
) -> list[dict]:
    week_case = _relative_week_case(mes)
    condition = ""
    params = {"anio": anio, "mes": mes, "semana": semana}
    if responsable is not None and responsable != "Todos":
        condition = " and pr.responsable = :responsable"
        params["responsable"] = responsable

    stmt = text(
        f"""
        select cp.producto_id as id,
               pr.prioridad as prioridad,
               case when pr.nombre is null then cp.producto_nombre else pr.nombre end as producto_nombre,
               (select max(corregido) from costos_planificacion pl where pl.producto_id = cp.producto_id and extract(year from pl.fecha) = extract(year from cp.fecha) and extract(month from pl.fecha) = extract(month from cp.fecha)) as planeado,
               pr.responsable,
               (select coalesce(sum(count), 0)
                  from panacea_sales_v2 s
                 where s.operation_year = extract(year from cp.fecha)
                   and s.operation_month = extract(month from cp.fecha)
                   and s.product_id = cp.producto_id
               )::int venta,
               to_char(fecha, 'YYYYMMDD') as codigo,
               cp.plan,
               cp.prod
          from costos_programacion cp
            join costos_productos pr
              on pr.id = cp.producto_id
             and pr.habilitado = true
         where extract(year from fecha) = :anio
           and extract(month from fecha) = :mes
           and (:semana = 0 or {week_case} = :semana)
         {condition}
         order by prioridad, producto_nombre, codigo
        """
    )
    result = await session.execute(stmt, params)
    rows = [dict(row) for row in result.mappings().all()]

    pivoted = []
    for pid, group in itertools.groupby(rows, key=lambda r: r["id"]):
        items = list(group)
        item = {
            "id": pid,
            "producto_nombre": items[0]["producto_nombre"],
            "planeado": items[0]["planeado"],
            "responsable": items[0]["responsable"],
            "venta": items[0]["venta"],
        }
        for d in items:
            item[f"{d['codigo']}-P"] = d["plan"]
            item[f"{d['codigo']}-E"] = d["prod"]
        pivoted.append(item)
    return pivoted


async def get_programacion_columnas(session: AsyncSession, anio: int, mes: int, semana: int) -> list[dict]:
    week_case = _relative_week_case(mes)
    stmt = text(
        f"""
        select distinct {week_case} as semana,
               case
                    when extract(dow from fecha::date) = 1 then 'Lun'
                    when extract(dow from fecha::date) = 2 then 'Mar'
                    when extract(dow from fecha::date) = 3 then 'Mie'
                    when extract(dow from fecha::date) = 4 then 'Jue'
                    when extract(dow from fecha::date) = 5 then 'Vie'
                    when extract(dow from fecha::date) = 6 then 'Sab'
               end as dia_de_la_semana,
               to_char(fecha, 'YYYYMMDD') as codigo
          from costos_programacion cp
         where extract(year from fecha) = :anio
           and extract(month from fecha) = :mes
           and (:semana = 0 or {week_case} = :semana)
         order by codigo
        """
    )
    result = await session.execute(stmt, {"anio": anio, "mes": mes, "semana": semana})
    rows = result.mappings().all()

    res = [
        {
            "headerName": "",
            "children": [
                {"field": "id", "hide": True},
                {"field": "producto", "hide": True},
                {"field": "producto_nombre", "width": 200, "headerName": "Producto", "pinned": "left"},
                {"field": "venta", "width": 70, "headerName": "Venta", "pinned": "left"},
                {"field": "planeado", "width": 70, "headerName": "Plan", "pinned": "left"},
                {
                    "valueGetter": 'parseInt(getValue("planeado") / 4)',
                    "width": 70,
                    "headerName": "Semanal",
                    "pinned": "left",
                },
                {"field": "responsable", "editable": True, "headerName": "Responsable", "width": 150},
            ],
        }
    ]

    for semana_num, group in itertools.groupby(rows, key=lambda r: r["semana"]):
        children = [
            {
                "headerName": d["dia_de_la_semana"],
                "children": [
                    {"field": f"{d['codigo']}-P", "editable": True, "headerName": "P", "cellStyle": {"backgroundColor": "silver"}},
                    {"field": f"{d['codigo']}-E", "editable": True, "headerName": "E"},
                ],
            }
            for d in group
        ]
        res.append({"headerName": f"Semana {semana_num}", "children": children})
    return res


_FIELD_MAP = {"P": "plan", "E": "prod"}


async def update_programacion(session: AsyncSession, data: list[dict]) -> None:
    for item in data:
        producto_id = item.get("id")
        producto = await session.get(Productos, producto_id)
        if producto is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Producto {producto_id} not found")
        if "responsable" in item:
            producto.responsable = item["responsable"]
        for key, value in item.items():
            if key in ("id", "responsable", "planeado"):
                continue
            codigo, op = key.split("-")
            fecha = datetime.strptime(codigo, "%Y%m%d").date()
            column = _FIELD_MAP.get(op)
            if column is None:
                continue
            row = (
                await session.execute(
                    select(Programacion).where(Programacion.producto_id == producto_id, Programacion.fecha == fecha)
                )
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No programacion row for producto_id={producto_id}, fecha={fecha}",
                )
            setattr(row, column, None if value == "" else value)
    await session.commit()


def _previous_calendar_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


async def _eligible_producto_ids_for_generation(session: AsyncSession) -> set[int]:
    result = await session.execute(select(Planificacion.producto_id).distinct())
    enrolled = {pid for (pid,) in result.all() if pid is not None}
    result = await session.execute(
        select(Productos.id).where(Productos.habilitado.is_(True), Productos.is_producto.is_(True))
    )
    eligible_flags = {pid for (pid,) in result.all()}
    return enrolled & eligible_flags


async def generate_programacion(
    session: AsyncSession,
    year: int,
    month: int,
    prev_year: int | None,
    prev_month: int | None,
    producto_id: int | None,
    dry_run: bool = True,
) -> dict:
    if prev_year is None or prev_month is None:
        prev_year, prev_month = _previous_calendar_month(year, month)

    eligible = await _eligible_producto_ids_for_generation(session)

    if producto_id is not None:
        if producto_id not in eligible:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="producto not enrolled in planning, not habilitado, or not is_producto",
            )
        candidate_ids = [producto_id]
    else:
        candidate_ids = list(eligible)

    productos_by_id: dict[int, Productos] = {}
    if candidate_ids:
        result = await session.execute(select(Productos).where(Productos.id.in_(candidate_ids)))
        productos_by_id = {p.id: p for p in result.scalars().all()}

    days_in_month = calendar.monthrange(year, month)[1]
    business_days = [
        date(year, month, day) for day in range(1, days_in_month + 1) if date(year, month, day).weekday() != 6
    ]  # Python Monday=0..Sunday=6; exclude Sunday, matching the reference's "day_of_week != Sunday"

    existing_days: set[tuple[int, date]] = set()
    if candidate_ids:
        # business_days always has at least ~24 entries for a real month
        # (only Sundays are excluded), so no empty-list guard is needed here.
        result = await session.execute(
            select(Programacion.producto_id, Programacion.fecha).where(
                Programacion.producto_id.in_(candidate_ids),
                Programacion.fecha >= business_days[0],
                Programacion.fecha <= business_days[-1],
            )
        )
        existing_days = {(pid, fecha) for pid, fecha in result.all()}

    day_row_inserts = []
    for day in business_days:
        for pid in candidate_ids:
            if (pid, day) not in existing_days:
                day_row_inserts.append(
                    {
                        "responsable": "Todos",
                        "plan": None,
                        "prod": None,
                        "producto_id": pid,
                        "producto_nombre": productos_by_id[pid].nombre,
                        "fecha": day,
                    }
                )

    # Correction candidates are "every product with >=1 planificacion row"
    # (not gated by habilitado/is_producto like day-row generation).
    if producto_id is not None:
        correction_candidates = [producto_id]
    else:
        result = await session.execute(select(Planificacion.producto_id).distinct())
        correction_candidates = [pid for (pid,) in result.all() if pid is not None]

    correction_updates = []
    if correction_candidates:
        # Batched (4 queries total) rather than per-product (4 * N queries)
        # — a bulk call across ~75+ enrolled products was taking 600+
        # sequential round-trips against the pooled connection and timing
        # out in a production dry-run smoke test before this fix.
        prev_agg = await session.execute(
            text(
                "select producto_id, max(plan) as prev_plan, max(corregido) as prev_corr "
                "from costos_planificacion where producto_id = ANY(:pids) "
                "and extract(year from fecha) = :y and extract(month from fecha) = :m "
                "group by producto_id"
            ),
            {"pids": correction_candidates, "y": prev_year, "m": prev_month},
        )
        prev_by_pid = {r["producto_id"]: (r["prev_plan"], r["prev_corr"]) for r in prev_agg.mappings().all()}

        venta_agg = await session.execute(
            text(
                "select product_id, coalesce(sum(count), 0) as venta from panacea_sales_v2 "
                "where product_id = ANY(:pids) and operation_year = :y and operation_month = :m "
                "group by product_id"
            ),
            {"pids": correction_candidates, "y": prev_year, "m": prev_month},
        )
        venta_by_pid = {r["product_id"]: r["venta"] for r in venta_agg.mappings().all()}

        this_plan_agg = await session.execute(
            text(
                "select producto_id, max(plan) as this_plan from costos_planificacion "
                "where producto_id = ANY(:pids) and extract(year from fecha) = :y and extract(month from fecha) = :m "
                "group by producto_id"
            ),
            {"pids": correction_candidates, "y": year, "m": month},
        )
        this_plan_by_pid = {r["producto_id"]: r["this_plan"] for r in this_plan_agg.mappings().all()}

        fecha = date(year, month, 1)
        target_rows_result = await session.execute(
            select(Planificacion).where(
                Planificacion.producto_id.in_(correction_candidates), Planificacion.fecha == fecha
            )
        )
        target_row_by_pid = {row.producto_id: row for row in target_rows_result.scalars().all()}

        for pid in correction_candidates:
            prev_plan, prev_corr = prev_by_pid.get(pid, (None, None))
            prev_venta = venta_by_pid.get(pid, 0)
            this_plan = this_plan_by_pid.get(pid)

            if prev_venta == 0 or prev_plan is None or prev_plan <= 0 or prev_corr is None or prev_corr <= 0:
                corregido = 0
            else:
                ratio = prev_venta / prev_corr
                base_plan = this_plan if this_plan is not None else prev_venta
                denom = prev_plan if prev_plan is not None else prev_venta
                scale = base_plan / denom
                if ratio > 0.75 and prev_venta >= prev_corr:
                    corregido = int(scale * prev_venta)
                elif ratio > 0.75 and prev_venta < prev_corr:
                    corregido = int(scale * prev_corr)
                else:
                    corregido = int(scale * prev_venta + (prev_corr - prev_venta) / 2)

            target_row = target_row_by_pid.get(pid)
            if target_row is not None:
                correction_updates.append(
                    {"row": target_row, "producto_id": pid, "fecha": fecha, "corregido": corregido}
                )

    if dry_run:
        return {
            "day_rows_that_would_be_inserted": [{k: v for k, v in r.items()} for r in day_row_inserts],
            "corregido_updates_that_would_apply": [
                {"producto_id": u["producto_id"], "fecha": u["fecha"], "corregido": u["corregido"]}
                for u in correction_updates
            ],
        }

    for row in day_row_inserts:
        session.add(Programacion(**row))
    for update in correction_updates:
        update["row"].corregido = update["corregido"]
        update["row"].sistema = update["corregido"]
    await session.commit()
    return {"day_rows_inserted": len(day_row_inserts), "corrections_applied": len(correction_updates)}


async def copy_week(
    session: AsyncSession, from_year: int, from_week: int, to_year: int, to_week: int, dry_run: bool = True
) -> dict:
    if (from_year, from_week) == (to_year, to_week):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source and target week must differ")

    target_rows = (
        await session.execute(
            text(
                "select id, producto_id, fecha, plan from costos_programacion "
                "where extract(isoyear from fecha) = :y and extract(week from fecha) = :w"
            ),
            {"y": to_year, "w": to_week},
        )
    ).mappings().all()

    if not target_rows:
        return {"updates": [], "warning": "no programacion rows exist for target week — nothing to copy into"}

    # Batched (2 queries total) rather than one source-lookup query per
    # target row — a real target week had 614 rows, which at one
    # round-trip each hung a production dry-run smoke test indefinitely
    # against the pooled (network-latency-bound) connection.
    source_rows = (
        await session.execute(
            text(
                "select producto_id, fecha, plan from costos_programacion "
                "where extract(isoyear from fecha) = :y and extract(week from fecha) = :w"
            ),
            {"y": from_year, "w": from_week},
        )
    ).mappings().all()
    source_by_key = {(r["producto_id"], r["fecha"].isoweekday()): r["plan"] for r in source_rows}

    updates = []
    unmatched = []
    for row in target_rows:
        key = (row["producto_id"], row["fecha"].isoweekday())
        if key in source_by_key:
            updates.append(
                {"id": row["id"], "producto_id": row["producto_id"], "fecha": row["fecha"], "plan": source_by_key[key]}
            )
        else:
            unmatched.append({"producto_id": row["producto_id"], "fecha": row["fecha"]})

    if dry_run:
        return {
            "updates_that_would_apply": [{k: v for k, v in u.items() if k != "id"} for u in updates],
            "skipped_no_source_match": unmatched,
        }

    if updates:
        await session.execute(
            text("update costos_programacion set plan = :plan where id = :id"),
            [{"plan": u["plan"], "id": u["id"]} for u in updates],
        )
    await session.commit()
    return {"updated": len(updates), "skipped_no_source_match": len(unmatched)}
