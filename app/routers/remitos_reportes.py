from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import get_session
from app.models.remitos import RemitoDetalles, Remitos
from app.schemas.remitos import RemitoRead
from app.schemas.remitos_reportes import (
    ProductoPendienteItem,
    ProductosPendientesPorDia,
    RemitosPendientesPorDia,
    ResponsableProductosPendientes,
)

router = APIRouter(prefix="/remitos-reportes", tags=["remitos-reportes"])

# Matches panacea-mayorista-backend's pendientes_por_dia bucketing exactly:
# en_produccion and preparando merge into one "en preparación" bucket, and
# facturado (its terminal state) counts as "entregados".
_ESTADO_COUNT_FIELD = {
    "creado": "total_pendientes",
    "en_produccion": "total_en_preparacion",
    "preparando": "total_en_preparacion",
    "listo_entregar": "total_listo_para_entrega",
    "en_entrega": "total_en_camino",
    "facturado": "total_entregados",
}


def _remitos_stmt():
    return select(Remitos).options(
        selectinload(Remitos.detalles).selectinload(RemitoDetalles.producto)
    )


@router.get("/pendientes-entrega", response_model=list[RemitoRead])
async def pendientes_entrega(session: AsyncSession = Depends(get_session)):
    stmt = _remitos_stmt().order_by(Remitos.fecha_entrega)
    result = await session.execute(stmt)
    return [RemitoRead.from_orm_row(row) for row in result.unique().scalars().all()]


@router.get("/pendientes-por-dia", response_model=list[RemitosPendientesPorDia])
async def pendientes_por_dia(
    fecha_desde: datetime | None = Query(None, description="Filter by fecha_entrega >= fecha_desde"),
    fecha_hasta: datetime | None = Query(None, description="Filter by fecha_entrega <= fecha_hasta"),
    session: AsyncSession = Depends(get_session),
):
    stmt = _remitos_stmt()
    if fecha_desde:
        stmt = stmt.where(Remitos.fecha_entrega >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(Remitos.fecha_entrega <= fecha_hasta)
    stmt = stmt.order_by(Remitos.fecha_entrega)
    result = await session.execute(stmt)
    remitos = result.unique().scalars().all()

    grouped: dict[str, list[Remitos]] = defaultdict(list)
    for remito in remitos:
        grouped[remito.fecha_entrega.strftime("%Y-%m-%d")].append(remito)

    report = []
    for fecha, items in sorted(grouped.items()):
        counts = {field: 0 for field in _ESTADO_COUNT_FIELD.values()}
        for remito in items:
            counts[_ESTADO_COUNT_FIELD[remito.estado]] += 1
        report.append(
            RemitosPendientesPorDia(
                fecha=fecha,
                total_remitos=len(items),
                remitos=[RemitoRead.from_orm_row(r) for r in items],
                **counts,
            )
        )
    return report


@router.get("/productos-pendientes-por-dia", response_model=list[ProductosPendientesPorDia])
async def productos_pendientes_por_dia(
    fecha_desde: date | None = Query(None, description="Filter by fecha_entrega >= fecha_desde (YYYY-MM-DD)"),
    fecha_hasta: date | None = Query(None, description="Filter by fecha_entrega <= fecha_hasta (YYYY-MM-DD)"),
    session: AsyncSession = Depends(get_session),
):
    sql = text(
        """
        SELECT
            DATE(r.fecha_entrega) AS fecha,
            p.responsable,
            p.nombre              AS producto,
            SUM(d.cantidad - COALESCE(d.entregado, 0)) AS cantidad
        FROM costos_remitodetalles d
        JOIN costos_remitos r   ON d.remito_id = r.id
        JOIN costos_productos p ON d.producto_id = p.id
        WHERE r.fecha_facturacion IS NULL
          AND (CAST(:fecha_desde AS date) IS NULL OR DATE(r.fecha_entrega) >= CAST(:fecha_desde AS date))
          AND (CAST(:fecha_hasta AS date) IS NULL OR DATE(r.fecha_entrega) <= CAST(:fecha_hasta AS date))
        GROUP BY DATE(r.fecha_entrega), p.responsable, p.nombre
        ORDER BY fecha ASC, p.responsable ASC, p.nombre ASC
        """
    )
    result = await session.execute(sql, {"fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta})
    rows = result.mappings().all()

    by_fecha: dict[str, dict[str, list[ProductoPendienteItem]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        fecha_key = str(row["fecha"])
        by_fecha[fecha_key][row["responsable"]].append(
            ProductoPendienteItem(producto=row["producto"], cantidad=int(row["cantidad"]))
        )

    return [
        ProductosPendientesPorDia(
            fecha=fecha,
            responsables=[
                ResponsableProductosPendientes(responsable=resp, productos=productos)
                for resp, productos in sorted(responsables.items())
            ],
        )
        for fecha, responsables in sorted(by_fecha.items())
    ]
