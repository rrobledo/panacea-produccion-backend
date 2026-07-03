from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_produccion_by_category(session: AsyncSession, anio: int, mes: int) -> list[dict]:
    stmt = text(
        """
        with prog as (select
                pr.id, pr.ref_id, pr.nombre, pr.categoria, pr.responsable,
                sum(cp.prod) as prod,
                extract(month from cp.fecha) as mes,
                extract(year from cp.fecha) as anio
          from costos_programacion cp
            join costos_productos pr
              on pr.id = cp.producto_id
             and pr.habilitado = true
        where extract(year from cp.fecha) = :anio
          and extract(month from cp.fecha) = :mes
        group by pr.id, pr.ref_id, nombre, categoria, pr.responsable, extract(year from cp.fecha), extract(month from cp.fecha)),
        data as (select pr.nombre, pr.categoria, pr.responsable,
                (select max(corregido) from costos_planificacion pl where pl.producto_id = pr.id and extract(year from fecha) = pr.anio and extract(month from fecha) = pr.mes) as plan,
                pr.prod,
                (select coalesce(sum(count), 0)
                  from panacea_sales_v2 s
                 where s.operation_year = pr.anio
                   and s.operation_month = pr.mes
                   and s.product_id = pr.id
                )::int vendido
          from prog pr)
        select categoria,
                sum(plan)::int as planeado,
                sum(prod)::int as producido,
                sum(vendido)::int as vendido,
                (round(sum(prod)::decimal / sum(plan)::decimal * 100, 2))::float as porcentaje_ejecutado,
                (round(sum(vendido)::decimal / sum(plan)::decimal * 100, 2))::float as porcentaje_vendido
          from data
        group by categoria
        having sum(plan)::decimal > 0
        order by categoria
        """
    )
    result = await session.execute(stmt, {"anio": anio, "mes": mes})
    return [dict(row) for row in result.mappings().all()]


async def get_produccion_by_productos(session: AsyncSession, anio: int, mes: int) -> list[dict]:
    stmt = text(
        """
        with prog as (select
                pr.id, pr.ref_id, pr.nombre, pr.categoria, pr.responsable,
                sum(cp.prod) as prod,
                extract(month from cp.fecha) as mes,
                extract(year from cp.fecha) as anio
          from costos_programacion cp
            join costos_productos pr
              on pr.id = cp.producto_id
             and pr.habilitado = true
        where extract(year from cp.fecha) = :anio
          and extract(month from cp.fecha) = :mes
        group by pr.id, pr.ref_id, nombre, categoria, pr.responsable, extract(year from cp.fecha), extract(month from cp.fecha)),
        data as (select pr.nombre, pr.id, pr.mes, pr.categoria, pr.responsable,
                (select max(corregido) from costos_planificacion pl where pl.producto_id = pr.id and extract(year from fecha) = pr.anio and extract(month from fecha) = pr.mes) as plan,
                pr.prod,
                (select coalesce(sum(count), 0)
                  from panacea_sales_v2 s
                 where s.operation_year = pr.anio
                   and s.operation_month = pr.mes
                   and s.product_id = pr.id
                )::int vendido
          from prog pr
            join planificacion2024 p
                on p.codigo = pr.ref_id::int)
        select categoria,
                nombre as producto,
                sum(plan)::int as planeado,
                sum(prod)::int as producido,
                sum(vendido)::int as vendido,
                (round(sum(prod)::decimal / sum(plan)::decimal * 100, 2))::float as porcentaje_ejecutado,
                (round(sum(vendido)::decimal / sum(plan)::decimal * 100, 2))::float as porcentaje_vendido
          from data
        group by categoria, nombre
        having sum(distinct plan)::decimal > 0
        order by categoria, nombre
        """
    )
    result = await session.execute(stmt, {"anio": anio, "mes": mes})
    return [dict(row) for row in result.mappings().all()]


async def get_insumos_by_month(
    session: AsyncSession, anio: int, mes: int, semana: int = 0, by_week: bool = True
) -> list[dict]:
    month_start = date(anio, mes, 2)
    sql_base = """
        with prog as (select
                cp.producto_id, pr.id, pr.ref_id, pr.nombre, pr.categoria, pr.responsable,
                sum(cp.prod) as prod,
                sum(cp.plan) as plan,
                extract(month from cp.fecha) as mes,
                extract(year from cp.fecha) as anio,
                extract('week' from fecha) - extract('week' from CAST(:month_start AS date)) + 1 as semana
          from costos_programacion cp
            join costos_productos pr
              on pr.id = cp.producto_id
             and pr.habilitado = true
        where extract(year from cp.fecha) = :anio
          and extract(month from cp.fecha) = :mes
        group by cp.producto_id, pr.id, pr.ref_id, nombre, categoria, pr.responsable, extract(year from cp.fecha), extract(month from cp.fecha), semana),
        data as (select pr.producto_id, pr.nombre, pr.categoria, pr.responsable,
                (select max(corregido) from costos_planificacion pl where pl.producto_id = pr.id and extract(year from fecha) = pr.anio and extract(month from fecha) = pr.mes) as plan_mensual,
                pr.plan, pr.prod, mes, semana
          from prog pr)
    """
    params = {"anio": anio, "mes": mes, "month_start": month_start, "semana": semana}
    if by_week:
        stmt = text(
            sql_base
            + """
            , res as (
                select  semana,
                        ci.nombre as insumo,
                        round(sum(cc.cantidad::decimal / p.lote_produccion::decimal * d.plan::decimal), 2) as plan,
                        round(sum(cc.cantidad::decimal / p.lote_produccion::decimal * d.prod::decimal), 2) as usado,
                        round((sum(cc.cantidad::decimal / p.lote_produccion::decimal * d.plan::decimal) / ci.cantidad * ci.precio)::decimal, 2) as plan_precio,
                        round((sum(cc.cantidad::decimal / p.lote_produccion::decimal * d.prod::decimal) / ci.cantidad * ci.precio)::decimal, 2) as usado_precio
                  from data d
                    join costos_productos p
                      on d.producto_id = p.id
                     and p.habilitado = true
                    join costos_costos cc
                      on d.producto_id = cc.producto_id
                    join costos_insumos ci
                      on ci.id = cc.insumo_id
                where :semana = 0 or semana = :semana
                group by semana, ci.id)
            select semana, insumo, plan, usado, plan_precio, usado_precio from res
            union
            select 999, 'Total', null, null, sum(plan_precio), sum(usado_precio) from res
            order by 1, 2
            """
        )
    else:
        stmt = text(
            sql_base
            + """
            , res as (
                select  mes,
                        ci.nombre as insumo,
                        round(sum(cc.cantidad::decimal / p.lote_produccion::decimal * d.plan::decimal), 2) as plan,
                        round(sum(cc.cantidad::decimal / p.lote_produccion::decimal * d.prod::decimal), 2) as usado,
                        round((sum(cc.cantidad::decimal / p.lote_produccion::decimal * d.plan::decimal) / ci.cantidad * ci.precio)::decimal, 2) as plan_precio,
                        round((sum(cc.cantidad::decimal / p.lote_produccion::decimal * d.prod::decimal) / ci.cantidad * ci.precio)::decimal, 2) as usado_precio
                  from data d
                    join costos_productos p
                      on d.producto_id = p.id
                     and p.habilitado = true
                    join costos_costos cc
                      on d.producto_id = cc.producto_id
                    join costos_insumos ci
                      on ci.id = cc.insumo_id
                group by mes, ci.id)
            select mes, insumo, plan, usado, plan_precio, usado_precio from res
            union
            select 999, 'Total', null, null, sum(plan_precio), sum(usado_precio) from res
            order by 1, 2
            """
        )
    result = await session.execute(stmt, params)
    return [dict(row) for row in result.mappings().all()]


_CUSTOMER_NAMES = {999: "Panacea Carlos Paz", 0: "Panacea Villa Allende", 888: "Panacea Cordoba"}


async def get_ventas_por_cliente(session: AsyncSession, anio: int, mes: int, cliente: str = "Todos") -> list[dict]:
    # The reference (ventas.py::get_ventas_por_cliente) builds this SQL via
    # raw f-string interpolation of `cliente` — a real SQL-injection
    # vulnerability (anio/mes are int()-cast first so aren't exploitable,
    # but the string param isn't). Parameterized here instead; not
    # replicated.
    stmt = text(
        """
        with aux as (select concat(
               date_part('YEAR', date(operation_date))::varchar,
               '-',
               lpad(date_part('MONTH', date(operation_date))::varchar, 2 , '0') ,
               '-',
               case
                   when extract(day from operation_date) between 1 and 7 then '1'
                   when extract(day from operation_date) between 8 and 15 then '2'
                   when extract(day from operation_date) between 16 and 23 then '3'
                   when extract(day from operation_date) between 24 and 31 then '4'
               end) as week_of_month,
               case
                when customer_id = 999 then 'Panacea Carlos Paz'
                when customer_id = 0 then 'Panacea Villa Allende'
                when customer_id = 888 then 'Panacea Cordoba'
                else 'Dieteticas'
               end as cliente,
               sum(count) as cantidad,
               sum(case when operation_hour between 8 and 15 then count else 0 end) as cantidad_maniana,
               sum(case when operation_hour between 15 and 21 then count else 0 end) as cantidad_tarde,
               sum(subtotal) as subtotal,
               sum(case when operation_hour between 8 and 15 then subtotal else 0 end) as subtotal_maniana,
               sum(case when operation_hour between 15 and 21 then subtotal else 0 end) as subtotal_tarde,
               count(distinct document_id) as count
           from panacea_sales_v2
          where date_part('YEAR', date(operation_date)) = :anio
            and (:mes = 0 or date_part('MONTH', date(operation_date)) = :mes)
          group by 1, customer_id, customer
          ),
        res as (
        select substring(week_of_month, 0, 8) as week_of_month,
               'TOTAL' as cliente,
               sum(cantidad)::int as cantidad,
               sum(cantidad_maniana)::int as cantidad_maniana,
               sum(cantidad_tarde)::int as cantidad_tarde,
               sum(subtotal) as subtotal,
               sum(subtotal_maniana) as subtotal_maniana,
               sum(subtotal_tarde) as subtotal_tarde
          from aux
         group by substring(week_of_month, 0, 8)
        union
        select substring(week_of_month, 0, 8) as week_of_month,
               concat('',cliente),
               sum(cantidad)::int as cantidad,
               sum(cantidad_maniana)::int as cantidad_maniana,
               sum(cantidad_tarde)::int as cantidad_tarde,
               sum(subtotal) as subtotal,
               sum(subtotal_maniana) as subtotal_maniana,
               sum(subtotal_tarde) as subtotal_tarde
          from aux
         group by substring(week_of_month, 0, 8), cliente
         union
         select week_of_month,
               'SUBTOTAL' as cliente,
               sum(cantidad)::int as cantidad,
               sum(cantidad_maniana)::int as cantidad_maniana,
               sum(cantidad_tarde)::int as cantidad_tarde,
               sum(subtotal) as subtotal,
               sum(subtotal_maniana) as subtotal_maniana,
               sum(subtotal_tarde) as subtotal_tarde
          from aux
         group by week_of_month
         union
         select week_of_month,
               concat(' ',cliente) as cliente,
               sum(cantidad)::int as cantidad,
               sum(cantidad_maniana)::int as cantidad_maniana,
               sum(cantidad_tarde)::int as cantidad_tarde,
               sum(subtotal) as subtotal,
               sum(subtotal_maniana) as subtotal_maniana,
               sum(subtotal_tarde) as subtotal_tarde
          from aux
         group by week_of_month, cliente)
        select week_of_month,
               cliente,
               cantidad_maniana,
               cantidad_tarde,
               cantidad,
               round(subtotal_maniana::decimal, 2) as subtotal_maniana,
               round(subtotal_tarde::decimal, 2) as subtotal_tarde,
               round(subtotal::decimal, 2) as subtotal
          from res
         where (:cliente = 'Todos' or cliente = :cliente)
         order by week_of_month, cliente desc
        """
    )
    result = await session.execute(stmt, {"anio": anio, "mes": mes, "cliente": cliente})
    return [dict(row) for row in result.mappings().all()]
