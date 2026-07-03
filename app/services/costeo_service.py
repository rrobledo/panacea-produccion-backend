from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.productos import Costos, Productos
from app.services.personal_service import calcular_liquidacion

# Ported as-is from panacea-backend/vercel_app/settings.py — not env-configurable
# there either; a deliberate hardcoded business constant, not a secret.
COSTO_TOTAL_FABRICA = 15_000_000
COSTO_FABRICA = 4_800_000
SUELDO_BRUTO = 1_000_000
ALICUOTA_ART = 5
TOTAL_EMPLEADOS = 8
TOTAL_HORAS_FABRICA_MENSUAL = TOTAL_EMPLEADOS * 44 * 4


def _gen_costo_detalle(insumo_precio: float, insumo_cantidad: float, cantidad: float, cantidad_lotes: int, costo_total: float) -> dict:
    raw = insumo_precio / insumo_cantidad * cantidad * cantidad_lotes if insumo_cantidad else 0
    if insumo_cantidad * cantidad * cantidad_lotes > 0:
        return {
            "cantidad": cantidad * cantidad_lotes,
            "costo_individual": round(raw, 2),
            "porcentaje_del_total": round(raw / costo_total * 100, 2),
        }
    return {"cantidad": cantidad * cantidad_lotes, "costo_individual": 1, "porcentaje_del_total": 1}


async def get_cost_by_product(
    session: AsyncSession,
    producto_id: int,
    cantidad_lotes: int | None = None,
    lote_produccion: int | None = None,
    utilidad: float | None = None,
    precio_actual: float | None = None,
) -> dict:
    prod = await session.get(Productos, producto_id)
    if prod is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto not found")

    # Costos.insumo is lazy="joined", so this already eager-loads via a JOIN.
    result = await session.execute(select(Costos).where(Costos.producto_id == producto_id))
    cost_detail = result.scalars().all()

    cantidad_lotes = cantidad_lotes or 1
    lote_produccion = (lote_produccion if lote_produccion is not None else prod.lote_produccion) * cantidad_lotes
    utilidad = utilidad if utilidad is not None else prod.utilidad
    precio_actual = precio_actual if precio_actual is not None else prod.precio_actual

    sum_cost = sum(
        (
            d.insumo.precio / d.insumo.cantidad * d.cantidad * cantidad_lotes
            if d.insumo.cantidad * d.cantidad * cantidad_lotes > 0
            else 1
        )
        for d in cost_detail
    )
    if sum_cost <= 0:
        sum_cost = 1

    precio_sugerido = round(sum_cost / lote_produccion * ((utilidad / 100) + 1), 2)
    costo_unitario_mp = round(sum_cost / lote_produccion, 2)
    margen_utilidad = round(((precio_actual / sum_cost * lote_produccion) - 1) * 100, 2)
    lotes_mensuales = int(TOTAL_HORAS_FABRICA_MENSUAL / prod.tiempo_produccion)
    venta_estimada_mensual = round(lote_produccion * lotes_mensuales * precio_actual, 2)
    costo_estimado_mensual = round(lote_produccion * lotes_mensuales * costo_unitario_mp, 2)
    prod_utilidad_mensual = round(venta_estimada_mensual - costo_estimado_mensual, 2)
    total_utilidad_mensual = round(prod_utilidad_mensual - COSTO_TOTAL_FABRICA, 2)
    utilidad_mensual = round(((venta_estimada_mensual / (costo_estimado_mensual + COSTO_TOTAL_FABRICA)) - 1) * 100, 2)

    liquidacion = calcular_liquidacion(sueldo_bruto=SUELDO_BRUTO, descuento_sindical=0, alicuota_art=ALICUOTA_ART)
    costo_mo = prod.tiempo_produccion * liquidacion["costo_hora"]
    costo_fab = prod.tiempo_produccion * (COSTO_FABRICA / TOTAL_HORAS_FABRICA_MENSUAL)

    detalle_costo = [
        {"insumo_nombre": d.insumo.nombre, **_gen_costo_detalle(d.insumo.precio, d.insumo.cantidad, d.cantidad, cantidad_lotes, sum_cost)}
        for d in cost_detail
    ]
    detalle_costo.sort(key=lambda x: x["porcentaje_del_total"], reverse=True)

    return {
        "producto_nombre": prod.nombre,
        "lote_produccion": lote_produccion,
        "tiempo_produccion": prod.tiempo_produccion,
        "utilidad": utilidad,
        "precio_actual": precio_actual,
        "precio_sugerido": round(precio_sugerido, 2),
        "costo_unitario_mp": costo_unitario_mp,
        "costo_unitario_mo": round(costo_mo / lote_produccion, 2),
        "costo_unitario_fab": round(costo_fab / lote_produccion, 2),
        "costo_lote_mp": round(costo_unitario_mp * lote_produccion, 2),
        "costo_lote_mo": round(costo_mo, 2),
        "costo_lote_fab": round(costo_fab, 2),
        "venta_estimada_lote": round(precio_actual * lote_produccion, 2),
        "margen_utilidad": margen_utilidad,
        "utilidad_del_lote": round((precio_actual * lote_produccion) - (costo_unitario_mp * lote_produccion), 2),
        "venta_estimada_mensual": venta_estimada_mensual,
        "costo_estimado_mensual": costo_estimado_mensual,
        "prod_utilidad_mensual": prod_utilidad_mensual,
        "total_utilidad_mensual": total_utilidad_mensual,
        "utilidad_mensual": utilidad_mensual,
        "lotes_mensuales": lotes_mensuales,
        "detalle_costo": detalle_costo,
    }


async def get_all_cost(
    session: AsyncSession,
    cantidad_lotes: int | None = None,
    lote_produccion: int | None = None,
    utilidad: float | None = None,
    precio_actual: float | None = None,
) -> list[dict]:
    result = await session.execute(select(Productos))
    productos = result.scalars().all()

    summaries = []
    for producto in productos:
        if producto.lote_produccion <= 1:
            continue
        cost = await get_cost_by_product(session, producto.id, cantidad_lotes, lote_produccion, utilidad, precio_actual)
        cost.pop("detalle_costo")
        summaries.append({"producto_id": producto.id, **cost})

    summaries.sort(key=lambda x: x["producto_nombre"])
    return summaries


async def get_precio_productos(session: AsyncSession, mes: int | None = None) -> list[dict]:
    mes = mes or datetime.now().month

    stmt = text(
        """
        with t as (
        select p.id as producto_id,
               p.prioridad as prioridad,
               p.nombre as producto_nombre,
               (select af.nombre
                 from costos_productosref cp
                    join articulos_final af
                      on cp.ref_id::int = af.idarticulo
                     and af.idarticulo < 2000
                     and af.activo = 1
                where cp.producto_id = p.id
                order by af.idarticulo
                limit 1) as articulo_va,
                (select af.nombre
                 from costos_productosref cp
                    join articulos_final af
                      on cp.ref_id::int = af.idarticulo
                     and af.idarticulo >= 2000
                     and af.activo = 1
                where cp.producto_id = p.id
                order by af.idarticulo
                limit 1) as articulo_cp,
                (select af.precio
                 from costos_productosref cp
                    join articulos_final af
                      on cp.ref_id::int = af.idarticulo
                     and af.idarticulo < 2000
                     and af.activo = 1
                where cp.producto_id = p.id
                order by af.idarticulo
                limit 1)::float as precio_va,
                (select af.precio
                 from costos_productosref cp
                    join articulos_final af
                      on cp.ref_id::int = af.idarticulo
                     and af.idarticulo >= 2000
                     and af.activo = 1
                where cp.producto_id = p.id
                order by af.idarticulo
                limit 1)::float as precio_cp,
                coalesce((select corregido
                  from costos_planificacion pl
                 where pl.producto_id = p.id
                   and extract(year from pl.fecha) = extract(year from current_date)
                   and extract(month from pl.fecha) = :mes), 0) as plan,
                p.precio_actual
           from costos_productos p
          where p.habilitado = true
            and p.is_producto = true
        )
        select producto_id,
               producto_nombre,
               articulo_va,
               articulo_cp,
               case
                when precio_va = 0 then precio_actual
                else precio_va
               end as precio_va,
               case
                when precio_cp = 0 then precio_actual
                else precio_cp
               end as precio_cp,
               plan
         from t
        order by prioridad, producto_nombre
        """
    )
    result = await session.execute(stmt, {"mes": mes})
    data = [dict(row) for row in result.mappings().all()]

    for prod in data:
        cost = await get_cost_by_product(session, prod["producto_id"])
        prod["costo_unitario_mp"] = cost["costo_unitario_mp"]
        prod["costo_unitario_mo"] = cost["costo_unitario_mo"]
        prod["costo_unitario_fab_new"] = cost["costo_unitario_fab"]
        prod["costo_unitario_fab"] = round(COSTO_TOTAL_FABRICA / (cost["lotes_mensuales"] * cost["lote_produccion"]), 2)
        prod["costo_total"] = prod["costo_unitario_mp"] + prod["costo_unitario_fab"]
        prod["costo_total_new"] = round(prod["costo_unitario_mp"] + prod["costo_unitario_mo"] + prod["costo_unitario_fab_new"], 2)
        prod["precio_sugerido"] = round(prod["costo_total_new"] / 0.70, 2) if prod["costo_total_new"] > 0 else 0.00

        if prod["precio_va"] and prod["costo_total"] > 0:
            prod["porcentaje_va"] = round(((prod["precio_va"] / prod["costo_total"]) - 1) * 100, 2)
            prod["ganancia_va"] = round(prod["precio_va"] - prod["costo_total"], 2) or 0
        else:
            prod["precio_va"] = 0
            prod["porcentaje_va"] = None
            prod["ganancia_va"] = 0

        if prod["precio_cp"] and prod["costo_total"] > 0:
            prod["porcentaje_cp"] = round(((prod["precio_cp"] / prod["costo_total"]) - 1) * 100, 2)
            prod["ganancia_cp"] = round(prod["precio_cp"] - prod["costo_total"], 2) or 0
        else:
            prod["precio_cp"] = 0
            prod["porcentaje_cp"] = None
            prod["ganancia_cp"] = 0

        if prod["precio_sugerido"] and prod["costo_total"] > 0:
            prod["porcentaje_sugerido"] = round(((prod["precio_sugerido"] / prod["costo_total_new"]) - 1) * 100, 2)
            prod["ganancia_sugerido"] = round(prod["precio_sugerido"] - prod["costo_total_new"], 2) or 0
        else:
            prod["precio_sugerido"] = 0
            prod["porcentaje_sugerido"] = 0
            prod["ganancia_sugerido"] = 0

        prod["ganancia_fab"] = round(prod.get("plan", 0) * prod["ganancia_va"] * 0.8, 2) if prod["ganancia_va"] else 0
        prod["ganancia_fab_new"] = round(prod.get("plan", 0) * prod["ganancia_sugerido"] * 0.8, 2) if prod["ganancia_sugerido"] else 0
        prod["precio_sugerido_final"] = round(prod["precio_sugerido"] / 0.60, 2) if prod["precio_sugerido"] > 0 else 0.00

    ganancia_total_fab = sum(int(d.get("ganancia_fab") or 0) for d in data)
    ganancia_total_fab_new = sum(int(d.get("ganancia_fab_new") or 0) for d in data)

    data.append(
        {
            "producto_id": 0,
            "producto_nombre": "TOTALES",
            "precio_va": 0,
            "precio_cp": 0,
            "precio_sugerido": 0,
            "precio_sugerido_final": 0,
            "costo_unitario_mp": 0,
            "costo_unitario_fab": 0,
            "costo_unitario_mo": 0,
            "costo_unitario_fab_new": 0,
            "costo_total": 0,
            "costo_total_new": 0,
            "porcentaje_va": 0,
            "ganancia_va": 0,
            "porcentaje_cp": 0,
            "ganancia_cp": 0,
            "ganancia_fab": ganancia_total_fab,
            "ganancia_fab_new": ganancia_total_fab_new,
        }
    )
    return data
