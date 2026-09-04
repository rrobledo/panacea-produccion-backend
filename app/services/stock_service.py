from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insumos import Insumos
from app.models.ordenes_produccion import OrdenProduccion, OrdenProduccionInsumoLinea
from app.models.stock_movimiento import StockMovimiento


async def crear_ajuste(session: AsyncSession, insumo: Insumos, cantidad: float, motivo: str) -> StockMovimiento:
    movimiento = StockMovimiento(
        insumo_id=insumo.id, tipo="AJUSTE", cantidad=cantidad, referencia=motivo, fecha=datetime.now(timezone.utc)
    )
    session.add(movimiento)
    insumo.cantidad = insumo.cantidad + cantidad
    await session.commit()
    await session.refresh(movimiento)
    return movimiento


def registrar_apertura(session: AsyncSession, insumo: Insumos, cantidad: float) -> StockMovimiento:
    # Deja un AJUSTE de apertura en el ledger para la cantidad inicial de un
    # insumo nuevo, sin volver a sumarla (ya viene seteada en el objeto) —
    # ver openspec/changes/ordenes-produccion-stock/design.md Decision 3 y
    # tasks.md 1.6 (mismo criterio usado para sembrar los insumos existentes).
    movimiento = StockMovimiento(
        insumo_id=insumo.id, tipo="AJUSTE", cantidad=cantidad, referencia="Apertura", fecha=datetime.now(timezone.utc)
    )
    session.add(movimiento)
    return movimiento


def crear_reserva(insumo_id: int, cantidad: float, referencia: str) -> StockMovimiento:
    # Sin commit — el caller (ordenes_produccion_service) confirma junto con
    # el resto de la transición de estado, ver design.md Decision 2.
    return StockMovimiento(
        insumo_id=insumo_id, tipo="RESERVA", cantidad=cantidad, referencia=referencia, fecha=datetime.now(timezone.utc)
    )


def crear_consumo(insumo: Insumos, cantidad: float, referencia: str) -> StockMovimiento:
    # RESERVA no toca insumos.cantidad (compromiso, no retiro físico);
    # CONSUMO sí — es el retiro físico real (ver design.md Decision 2).
    insumo.cantidad = insumo.cantidad - cantidad
    return StockMovimiento(
        insumo_id=insumo.id, tipo="CONSUMO", cantidad=-cantidad, referencia=referencia, fecha=datetime.now(timezone.utc)
    )


async def list_movimientos(session: AsyncSession, insumo_id: int) -> list[StockMovimiento]:
    stmt = (
        select(StockMovimiento)
        .where(StockMovimiento.insumo_id == insumo_id)
        .order_by(StockMovimiento.fecha.desc(), StockMovimiento.id.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_comprometido_map(session: AsyncSession, insumo_ids: list[int] | None = None) -> dict[int, float]:
    # Comprometido = insumo reservado por órdenes que todavía no llegaron a
    # EN_PRODUCCION/CANCELADA — no se deriva del ledger histórico de RESERVA
    # (que nunca se "cierra"), sino de las líneas de órdenes vivas en
    # ASIGNADA, más simple y sin ambigüedad temporal.
    stmt = (
        select(OrdenProduccionInsumoLinea.insumo_id, func.sum(OrdenProduccionInsumoLinea.cantidad))
        .join(OrdenProduccion, OrdenProduccion.id == OrdenProduccionInsumoLinea.orden_id)
        .where(OrdenProduccion.estado == "ASIGNADA")
        .group_by(OrdenProduccionInsumoLinea.insumo_id)
    )
    if insumo_ids is not None:
        stmt = stmt.where(OrdenProduccionInsumoLinea.insumo_id.in_(insumo_ids))
    result = await session.execute(stmt)
    return {insumo_id: float(total or 0) for insumo_id, total in result.all()}
