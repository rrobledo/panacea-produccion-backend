from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_campana import CrmCampana
from app.models.crm_contacto import CrmContacto
from app.models.crm_oportunidad import CrmEtapaVenta, CrmOportunidad
from app.models.crm_vendedor import CrmVendedor
from app.models.crm_visita import CrmVisita
from app.services import (
    crm_campana_service,
    crm_contacto_service,
    crm_erp_integration_service,
    crm_oportunidad_service,
    crm_visita_service,
)

_VALOR_CLIENTE_STMT = text(
    """
    SELECT COUNT(DISTINCT document_id) AS compras, COALESCE(SUM(subtotal), 0) AS total,
           MIN(operation_date) AS primera_compra, MAX(operation_date) AS ultima_compra
      FROM panacea_sales_v2
     WHERE customer_id = :cid
    """
)

_INACTIVOS_STMT = text(
    """
    SELECT c.id AS contacto_id, c.nombre, MAX(s.operation_date) AS ultima_compra
      FROM crm_contacto c
      JOIN panacea_sales_v2 s ON s.customer_id = c.erp_cliente_id
     WHERE c.erp_cliente_id IS NOT NULL
     GROUP BY c.id, c.nombre
    HAVING MAX(s.operation_date) < CURRENT_DATE - (:dias * INTERVAL '1 day')
    """
)


async def conversion_visitas_clientes(
    session: AsyncSession, fecha_desde: date | None = None, fecha_hasta: date | None = None
) -> dict:
    stmt = select(CrmVisita.contacto_id).distinct()
    if fecha_desde is not None:
        stmt = stmt.where(CrmVisita.fecha >= fecha_desde)
    if fecha_hasta is not None:
        stmt = stmt.where(CrmVisita.fecha <= fecha_hasta)
    contacto_ids = (await session.execute(stmt)).scalars().all()
    if not contacto_ids:
        return {"visitados": 0, "convertidos": 0, "porcentaje": 0.0}

    convertidos = (
        await session.execute(
            select(func.count())
            .select_from(CrmContacto)
            .where(CrmContacto.id.in_(contacto_ids), CrmContacto.erp_cliente_id.is_not(None))
        )
    ).scalar_one()
    total = len(contacto_ids)
    return {"visitados": total, "convertidos": convertidos, "porcentaje": round(convertidos / total * 100, 2)}


async def cac(session: AsyncSession, fecha_desde: date, fecha_hasta: date) -> dict:
    costo_total = (
        await session.execute(
            select(func.coalesce(func.sum(CrmCampana.costo), 0)).where(
                CrmCampana.fecha_inicio <= fecha_hasta,
                or_(CrmCampana.fecha_fin.is_(None), CrmCampana.fecha_fin >= fecha_desde),
            )
        )
    ).scalar_one()
    clientes_nuevos = (
        await session.execute(
            select(func.count())
            .select_from(CrmContacto)
            .where(
                CrmContacto.erp_cliente_id.is_not(None),
                CrmContacto.created_at >= fecha_desde,
                CrmContacto.created_at <= fecha_hasta,
            )
        )
    ).scalar_one()
    costo_total = float(costo_total)
    return {
        "costo_total": costo_total,
        "clientes_nuevos": clientes_nuevos,
        "cac": costo_total / clientes_nuevos if clientes_nuevos else None,
    }


async def valor_cliente(session: AsyncSession, contacto_id: int) -> dict:
    contacto = await crm_contacto_service.get_contacto(session, contacto_id)
    if contacto.erp_cliente_id is None:
        return {"clv": 0.0, "ticket_promedio": None, "compras": 0, "primera_compra": None, "ultima_compra": None}

    row = (await session.execute(_VALOR_CLIENTE_STMT, {"cid": contacto.erp_cliente_id})).mappings().one()
    compras = row["compras"]
    total = float(row["total"])
    return {
        "clv": total,
        "ticket_promedio": total / compras if compras else None,
        "compras": compras,
        "primera_compra": row["primera_compra"],
        "ultima_compra": row["ultima_compra"],
    }


async def clientes_inactivos(session: AsyncSession, dias: int = 60) -> list[dict]:
    result = await session.execute(_INACTIVOS_STMT, {"dias": dias})
    return [dict(row) for row in result.mappings().all()]


async def ventas_por_ciudad(
    session: AsyncSession, fecha_desde: date | None = None, fecha_hasta: date | None = None
) -> list[dict]:
    where_extra, params = _fecha_where("s.operation_date", fecha_desde, fecha_hasta)
    stmt = text(
        f"""
        SELECT ci.nombre AS ciudad, COALESCE(SUM(s.subtotal), 0) AS total
          FROM crm_contacto c
          JOIN crm_ciudad ci ON ci.id = c.ciudad_id
          JOIN panacea_sales_v2 s ON s.customer_id = c.erp_cliente_id
         WHERE c.erp_cliente_id IS NOT NULL {where_extra}
         GROUP BY ci.nombre
         ORDER BY total DESC
        """
    )
    result = await session.execute(stmt, params)
    return [dict(row) for row in result.mappings().all()]


async def ventas_por_segmento(
    session: AsyncSession, fecha_desde: date | None = None, fecha_hasta: date | None = None
) -> list[dict]:
    where_extra, params = _fecha_where("s.operation_date", fecha_desde, fecha_hasta)
    stmt = text(
        f"""
        SELECT seg.nombre AS segmento, COALESCE(SUM(s.subtotal), 0) AS total
          FROM crm_contacto_segmento cs
          JOIN crm_segmento seg ON seg.id = cs.segmento_id
          JOIN crm_contacto c ON c.id = cs.contacto_id
          JOIN panacea_sales_v2 s ON s.customer_id = c.erp_cliente_id
         WHERE c.erp_cliente_id IS NOT NULL {where_extra}
         GROUP BY seg.nombre
         ORDER BY total DESC
        """
    )
    result = await session.execute(stmt, params)
    return [dict(row) for row in result.mappings().all()]


async def ventas_por_vendedor(
    session: AsyncSession, fecha_desde: date | None = None, fecha_hasta: date | None = None
) -> list[dict]:
    where_extra, params = _fecha_where("s.operation_date", fecha_desde, fecha_hasta)
    stmt = text(
        f"""
        WITH ultima_visita AS (
            SELECT DISTINCT ON (contacto_id) contacto_id, vendedor_id
              FROM crm_visita
             ORDER BY contacto_id, fecha DESC
        )
        SELECT v.nombre AS vendedor, COALESCE(SUM(s.subtotal), 0) AS total
          FROM crm_contacto c
          JOIN ultima_visita uv ON uv.contacto_id = c.id
          JOIN crm_vendedor v ON v.id = uv.vendedor_id
          JOIN panacea_sales_v2 s ON s.customer_id = c.erp_cliente_id
         WHERE c.erp_cliente_id IS NOT NULL {where_extra}
         GROUP BY v.nombre
         ORDER BY total DESC
        """
    )
    result = await session.execute(stmt, params)
    return [dict(row) for row in result.mappings().all()]


def _fecha_where(column: str, fecha_desde: date | None, fecha_hasta: date | None) -> tuple[str, dict]:
    clauses = []
    params: dict = {}
    if fecha_desde is not None:
        clauses.append(f"AND {column} >= :fecha_desde")
        params["fecha_desde"] = fecha_desde
    if fecha_hasta is not None:
        clauses.append(f"AND {column} <= :fecha_hasta")
        params["fecha_hasta"] = fecha_hasta
    return " ".join(clauses), params


async def roi_campana(session: AsyncSession, campana_id: int) -> dict:
    campana = await crm_campana_service.get_campana(session, campana_id)
    conversion = await crm_campana_service.get_conversion(session, campana_id)

    total_generado = float(
        (
            await session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(s.subtotal), 0)
                      FROM crm_contacto_campana cc
                      JOIN crm_contacto c ON c.id = cc.contacto_id
                      JOIN panacea_sales_v2 s ON s.customer_id = c.erp_cliente_id
                     WHERE cc.campana_id = :campana_id
                    """
                ),
                {"campana_id": campana_id},
            )
        ).scalar_one()
    )
    costo = float(campana.costo) if campana.costo is not None else None
    return {
        "campana_id": campana_id,
        "contactos_asociados": conversion.contactos_asociados,
        "contactos_con_erp": conversion.contactos_con_erp,
        "total_generado": total_generado,
        "costo": costo,
        "roi": (total_generado - costo) / costo if costo else None,
    }


async def dashboard_ejecutivo(session: AsyncSession, fecha_desde: date, fecha_hasta: date) -> dict:
    return {
        "conversion_visitas_clientes": await conversion_visitas_clientes(session, fecha_desde, fecha_hasta),
        "cac": await cac(session, fecha_desde, fecha_hasta),
        "ventas_por_ciudad": await ventas_por_ciudad(session, fecha_desde, fecha_hasta),
        "ventas_por_segmento": await ventas_por_segmento(session, fecha_desde, fecha_hasta),
        "ventas_por_vendedor": await ventas_por_vendedor(session, fecha_desde, fecha_hasta),
        "clientes_inactivos": len(await clientes_inactivos(session)),
    }


async def dashboard_vendedor(session: AsyncSession, vendedor_id: int) -> dict:
    if await session.get(CrmVendedor, vendedor_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendedor not found")

    visitas = await crm_visita_service.list_visitas(session)
    visitas = [v for v in visitas if v.vendedor_id == vendedor_id]
    contacto_ids = sorted({v.contacto_id for v in visitas}) or [-1]

    pipeline_rows = (
        await session.execute(
            select(CrmEtapaVenta.nombre, func.count(CrmOportunidad.id))
            .join(CrmOportunidad, CrmOportunidad.etapa_id == CrmEtapaVenta.id)
            .where(CrmOportunidad.contacto_id.in_(contacto_ids))
            .group_by(CrmEtapaVenta.nombre)
        )
    ).all()

    return {
        "vendedor_id": vendedor_id,
        "contactos_asignados": len(contacto_ids) if contacto_ids != [-1] else 0,
        "visitas": len(visitas),
        "pipeline": dict(pipeline_rows),
    }


async def dashboard_marketing(session: AsyncSession) -> dict:
    campanas = await crm_campana_service.list_campanas(session)
    campanas_kpis = [await roi_campana(session, campana.id) for campana in campanas]
    return {"campanas": campanas_kpis}


async def dashboard_contacto_360(session: AsyncSession, contacto_id: int) -> dict:
    contacto = await crm_contacto_service.get_contacto(session, contacto_id)
    visitas = await crm_visita_service.list_visitas(session, contacto_id=contacto_id)
    oportunidades = await crm_oportunidad_service.list_oportunidades(session, contacto_id=contacto_id)

    campanas_rows = (
        await session.execute(
            text(
                """
                SELECT camp.id, camp.nombre, cc.fecha_asociacion
                  FROM crm_contacto_campana cc
                  JOIN crm_campana camp ON camp.id = cc.campana_id
                 WHERE cc.contacto_id = :cid
                """
            ),
            {"cid": contacto_id},
        )
    ).mappings().all()

    proxima_actividad = (
        await session.execute(
            text(
                """
                SELECT a.tipo, a.fecha, a.notas
                  FROM crm_actividad a
                  JOIN crm_oportunidad o ON o.id = a.oportunidad_id
                 WHERE o.contacto_id = :cid AND a.fecha >= CURRENT_DATE
                 ORDER BY a.fecha
                 LIMIT 1
                """
            ),
            {"cid": contacto_id},
        )
    ).mappings().first()

    valor = await valor_cliente(session, contacto_id)
    historial = await crm_erp_integration_service.get_historial_compras(session, contacto_id)
    productos = await crm_erp_integration_service.get_productos_mas_consumidos(session, contacto_id)

    hace_12_meses = date.today() - timedelta(days=365)
    facturacion_12m = sum(
        row["total"] for row in historial if row["operation_date"] and row["operation_date"] >= hace_12_meses
    )

    return {
        "contacto": contacto,
        "campanas": [dict(row) for row in campanas_rows],
        "ultimas_visitas": visitas[:5],
        "pipeline": oportunidades,
        "ultimas_compras": historial[:5],
        "productos_favoritos": productos,
        "facturacion_12_meses": facturacion_12m,
        "frecuencia_compra": valor["compras"],
        "proxima_accion": dict(proxima_actividad) if proxima_actividad else None,
        "observaciones": contacto.observaciones,
    }
