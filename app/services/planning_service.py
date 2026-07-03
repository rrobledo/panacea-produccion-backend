import itertools
import math
from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.planificacion import Planificacion
from app.models.productos import Productos

MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


async def get_planning(session: AsyncSession, anio: int) -> list[dict]:
    stmt = text(
        """
        select cp.producto_id as id,
               pr.prioridad as prioridad,
               pr.nombre as producto_nombre,
               to_char(fecha, 'YYYYMM') as codigo,
               cp.plan, cp.sistema, cp.corregido,
               (select coalesce(sum(prod), 0)
                  from costos_programacion s
                 where extract(year from s.fecha) = extract(year from cp.fecha)
                   and extract(month from s.fecha) = extract(month from cp.fecha)
                   and s.producto_id = cp.producto_id
               )::int prod,
               (select coalesce(sum(count), 0)
                  from panacea_sales_v2 s
                 where s.operation_year = extract(year from cp.fecha)
                   and s.operation_month = extract(month from cp.fecha)
                   and s.product_id = cp.producto_id
               )::int venta
         from costos_planificacion cp
           join costos_productos pr
             on pr.id = cp.producto_id
            and pr.habilitado = true
         where extract(year from cp.fecha) = :anio
        union
        select 999 as id, 999 as prioridad, 'TOTAL' as producto_nombre,
               to_char(fecha, 'YYYYMM') as codigo,
               sum(cp.plan) as plan, sum(cp.sistema) as sistema, sum(cp.corregido) as corregido,
               sum((select coalesce(sum(prod), 0)
                  from costos_programacion s
                 where extract(year from s.fecha) = extract(year from cp.fecha)
                   and extract(month from s.fecha) = extract(month from cp.fecha)
                   and s.producto_id = cp.producto_id
               ))::int prod,
               sum((select coalesce(sum(count), 0)
                  from panacea_sales_v2 s
                 where s.operation_year = extract(year from cp.fecha)
                   and s.operation_month = extract(month from cp.fecha)
                   and s.product_id = cp.producto_id
               ))::int venta
         from costos_planificacion cp
           join costos_productos pr
             on pr.id = cp.producto_id
            and pr.habilitado = true
        where extract(year from cp.fecha) = :anio
        group by to_char(fecha, 'YYYYMM')
        order by prioridad, producto_nombre, codigo
        """
    )
    result = await session.execute(stmt, {"anio": anio})
    rows = [dict(row) for row in result.mappings().all()]

    pivoted = []
    for pid, group in itertools.groupby(rows, key=lambda r: r["id"]):
        items = list(group)
        item = {"id": pid, "producto_nombre": items[0]["producto_nombre"]}
        for d in items:
            item[f"{d['codigo']}-PLAN"] = d["plan"]
            item[f"{d['codigo']}-SISTEMA"] = d["sistema"]
            item[f"{d['codigo']}-CORREGIDO"] = d["corregido"]
            item[f"{d['codigo']}-PROD"] = d["prod"]
            item[f"{d['codigo']}-VENTA"] = d["venta"]
        pivoted.append(item)
    return pivoted


async def get_planning_columnas(session: AsyncSession, anio: int) -> list[dict]:
    stmt = text(
        """
        select distinct extract(month from cp.fecha) as mes,
               to_char(fecha, 'YYYYMM') as codigo
          from costos_planificacion cp
            join costos_productos pr
              on pr.id = cp.producto_id
             and pr.habilitado = true
         where extract(year from cp.fecha) = :anio
        order by codigo
        """
    )
    result = await session.execute(stmt, {"anio": anio})
    rows = result.mappings().all()

    children = []
    for d in rows:
        codigo = d["codigo"]
        children.append(
            {
                "headerName": MESES[int(d["mes"])],
                "children": [
                    {"field": f"{codigo}-PLAN", "editable": False, "headerName": "Plan", "cellStyle": {"backgroundColor": "silver"}},
                    {"field": f"{codigo}-SISTEMA", "editable": False, "headerName": "Sistema"},
                    {"field": f"{codigo}-CORREGIDO", "editable": True, "headerName": "Corr"},
                    {"field": f"{codigo}-PROD", "editable": False, "headerName": "Prod"},
                    {"field": f"{codigo}-VENTA", "editable": False, "headerName": "Venta"},
                ],
            }
        )

    return [
        {
            "headerName": "",
            "children": [
                {"field": "id", "hide": True},
                {"field": "producto", "hide": True},
                {"field": "producto_nombre", "width": 200, "headerName": "Producto", "pinned": "left"},
            ],
        },
        {"headerName": f"Anio {anio}", "children": children},
    ]


_FIELD_TO_COLUMN = {"PLAN": "plan", "SISTEMA": "sistema", "CORREGIDO": "corregido"}


async def update_planificacion(session: AsyncSession, data: list[dict]) -> None:
    for item in data:
        producto_id = item.get("id")
        for key, value in item.items():
            if key == "id":
                continue
            codigo, op = key.split("-")
            fecha = datetime.strptime(f"{codigo}01", "%Y%m%d").date()
            column = _FIELD_TO_COLUMN.get(op)
            if column is None:
                continue
            row = (
                await session.execute(
                    select(Planificacion).where(
                        Planificacion.producto_id == producto_id, Planificacion.fecha == fecha
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No planificacion row for producto_id={producto_id}, fecha={fecha}",
                )
            setattr(row, column, None if value == "" else value)
    await session.commit()


async def generate_planning(
    session: AsyncSession, year: int, producto_id: int | None, dry_run: bool = True
) -> dict:
    if year < 2000 or year > datetime.now().year + 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="year out of sane range")

    if producto_id is not None:
        producto = await session.get(Productos, producto_id)
        if producto is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto not found")
        if not producto.habilitado:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cannot generate planning for a disabled producto",
            )
        candidates = [producto]
    else:
        result = await session.execute(select(Productos).where(Productos.habilitado.is_(True)))
        candidates = list(result.scalars().all())

    existing: set[tuple[int, date]] = set()
    if candidates:
        existing_result = await session.execute(
            select(Planificacion.producto_id, Planificacion.fecha).where(
                Planificacion.producto_id.in_([p.id for p in candidates])
            )
        )
        existing = {(pid, fecha) for pid, fecha in existing_result.all()}

    planned_inserts: list[dict] = []
    prev_year = year - 1

    for producto in candidates:
        sales_result = await session.execute(
            text(
                "select operation_month, lugar_venta_id, sum(count) as venta "
                "from panacea_sales_v2 "
                "where product_id = :pid and operation_year = :prev_year "
                "group by operation_month, lugar_venta_id"
            ),
            {"pid": producto.id, "prev_year": prev_year},
        )
        sales_rows = sales_result.mappings().all()

        if not sales_rows:
            for month in range(1, 13):
                fecha = date(year, month, 1)
                if (producto.id, fecha) not in existing:
                    planned_inserts.append(
                        {"producto_id": producto.id, "fecha": fecha, "plan": 0, "sistema": 0, "indice": 0}
                    )
            continue

        ventas_mensual: dict[int, float] = {}
        ventas_mensual_x_lugar: dict[int, dict[int, float]] = {}
        for row in sales_rows:
            mes, lugar, venta = row["operation_month"], row["lugar_venta_id"], float(row["venta"])
            ventas_mensual[mes] = ventas_mensual.get(mes, 0) + venta
            ventas_mensual_x_lugar.setdefault(mes, {})[lugar] = ventas_mensual_x_lugar.get(mes, {}).get(lugar, 0) + venta

        promedio_venta = round(sum(ventas_mensual.values()) / len(ventas_mensual))

        lugares = {lugar for por_mes in ventas_mensual_x_lugar.values() for lugar in por_mes}
        promedio_venta_x_lugar: dict[int, float] = {}
        for lugar in lugares:
            valores = [por_mes[lugar] for por_mes in ventas_mensual_x_lugar.values() if lugar in por_mes]
            promedio_venta_x_lugar[lugar] = round(sum(valores) / len(valores)) if valores else 0

        indice_por_mes: dict[int, dict[int, float]] = {}
        for mes, por_lugar in ventas_mensual_x_lugar.items():
            for lugar, venta in por_lugar.items():
                lugar_avg = promedio_venta_x_lugar.get(lugar, 0)
                indice_por_mes.setdefault(mes, {})[lugar] = (venta / lugar_avg) if lugar_avg > 0 else 0

        for month in range(1, 13):
            fecha = date(year, month, 1)
            if (producto.id, fecha) in existing:
                continue
            if month not in indice_por_mes:
                planned_inserts.append(
                    {"producto_id": producto.id, "fecha": fecha, "plan": 0, "sistema": 0, "indice": 0}
                )
                continue
            avg_indice = sum(indice_por_mes[month].values()) / len(indice_por_mes[month])
            plan_value = math.ceil(promedio_venta * avg_indice / 10) * 10
            planned_inserts.append(
                {
                    "producto_id": producto.id,
                    "fecha": fecha,
                    "plan": plan_value,
                    "sistema": plan_value,
                    "indice": round(avg_indice, 2),
                }
            )

    if dry_run:
        return {"rows_that_would_be_inserted": planned_inserts, "count": len(planned_inserts)}

    for row in planned_inserts:
        session.add(Planificacion(**row))
    await session.commit()
    return {"rows_inserted": len(planned_inserts)}
