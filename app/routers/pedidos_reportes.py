from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import get_session
from app.models.pedido import Pedido, PedidoDetalle
from app.schemas.pedido import PedidoRead
from app.schemas.pedido_reportes import (
    PedidosPendientesPorDia,
    ProductoPendienteItem,
    ProductosPendientesPorDia,
    ResponsableProductosPendientes,
)

router = APIRouter(prefix="/pedidos-reportes", tags=["pedidos-reportes"])

# EN_PREPARACION and PREPARADO merge into one "en preparación" bucket, same
# as the legacy Remitos.estado report merged en_produccion/preparando —
# see design.md Decision 8. There's no bucket for Remito's own EN_TRANSITO
# (legacy "en_camino"): that concept now lives entirely on Remito, not on
# Pedido, and has no equivalent here.
_ESTADO_COUNT_FIELD = {
    "PENDIENTE": "total_pendientes",
    "EN_PREPARACION": "total_en_preparacion",
    "PREPARADO": "total_en_preparacion",
    "LISTO_PARA_ENTREGA": "total_listo_para_entrega",
    "ENTREGADO": "total_entregados",
    "CANCELADO": "total_cancelados",
}


def _pedidos_stmt():
    return select(Pedido).options(selectinload(Pedido.detalles).selectinload(PedidoDetalle.producto))


@router.get("/pendientes-entrega", response_model=list[PedidoRead])
async def pendientes_entrega(session: AsyncSession = Depends(get_session)):
    stmt = _pedidos_stmt().order_by(Pedido.fecha_entrega)
    result = await session.execute(stmt)
    return [PedidoRead.from_orm_row(row) for row in result.unique().scalars().all()]


@router.get("/pendientes-por-dia", response_model=list[PedidosPendientesPorDia])
async def pendientes_por_dia(
    fecha_desde: datetime | None = Query(None, description="Filter by fecha_entrega >= fecha_desde"),
    fecha_hasta: datetime | None = Query(None, description="Filter by fecha_entrega <= fecha_hasta"),
    session: AsyncSession = Depends(get_session),
):
    stmt = _pedidos_stmt()
    if fecha_desde:
        stmt = stmt.where(Pedido.fecha_entrega >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(Pedido.fecha_entrega <= fecha_hasta)
    stmt = stmt.order_by(Pedido.fecha_entrega)
    result = await session.execute(stmt)
    pedidos = result.unique().scalars().all()

    grouped: dict[str, list[Pedido]] = defaultdict(list)
    for pedido in pedidos:
        grouped[pedido.fecha_entrega.strftime("%Y-%m-%d")].append(pedido)

    report = []
    for fecha, items in sorted(grouped.items()):
        counts = {field: 0 for field in _ESTADO_COUNT_FIELD.values()}
        for pedido in items:
            counts[_ESTADO_COUNT_FIELD[pedido.estado]] += 1
        report.append(
            PedidosPendientesPorDia(
                fecha=fecha,
                total_pedidos=len(items),
                pedidos=[PedidoRead.from_orm_row(p) for p in items],
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
            DATE(p.fecha_entrega) AS fecha,
            prod.responsable,
            prod.nombre           AS producto,
            SUM(d.cantidad_pedida - d.cantidad_entregada) AS cantidad
        FROM pedidos_pedido_detalle d
        JOIN pedidos_pedido p       ON d.pedido_id = p.id
        JOIN costos_productos prod  ON d.producto_id = prod.id
        WHERE p.estado NOT IN ('ENTREGADO', 'CANCELADO')
          AND (CAST(:fecha_desde AS date) IS NULL OR DATE(p.fecha_entrega) >= CAST(:fecha_desde AS date))
          AND (CAST(:fecha_hasta AS date) IS NULL OR DATE(p.fecha_entrega) <= CAST(:fecha_hasta AS date))
        GROUP BY DATE(p.fecha_entrega), prod.responsable, prod.nombre
        ORDER BY fecha ASC, prod.responsable ASC, prod.nombre ASC
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
