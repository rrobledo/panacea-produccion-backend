from datetime import datetime, timezone

from fastapi import HTTPException, status
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


def crear_reserva(insumo_id: int, cantidad: float, referencia: str, orden_id: int | None = None) -> StockMovimiento:
    # Sin commit — el caller (ordenes_produccion_service) confirma junto con
    # el resto de la transición de estado, ver design.md Decision 2.
    return StockMovimiento(
        insumo_id=insumo_id,
        tipo="RESERVA",
        cantidad=cantidad,
        orden_id=orden_id,
        referencia=referencia,
        fecha=datetime.now(timezone.utc),
    )


def crear_consumo(
    insumo: Insumos, cantidad: float, referencia: str, orden_id: int | None = None
) -> StockMovimiento:
    # RESERVA no toca insumos.cantidad (compromiso, no retiro físico);
    # CONSUMO sí — es el retiro físico real (ver design.md Decision 2).
    insumo.cantidad = insumo.cantidad - cantidad
    return StockMovimiento(
        insumo_id=insumo.id,
        tipo="CONSUMO",
        cantidad=-cantidad,
        orden_id=orden_id,
        referencia=referencia,
        fecha=datetime.now(timezone.utc),
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


# ── Stock de artículos producidos (F2b de masa-procesos-y-maquinaria) ────────
#
# A diferencia de los insumos, que materializan su saldo en `insumos.cantidad`,
# el disponible de un artículo producido se **deriva** sumando su ledger. No hay
# campo que mantener sincronizado, así que no puede desincronizarse: es la
# ventaja de empezar de cero en vez de heredar un número editado a mano.


def crear_produccion(producto_id: int, cantidad: float, referencia: str, orden_id: int | None = None) -> StockMovimiento:
    """Lo que una orden finalizada fabricó. Sin commit: lo confirma el caller."""
    return StockMovimiento(
        producto_id=producto_id,
        tipo="PRODUCCION",
        cantidad=cantidad,
        orden_id=orden_id,
        referencia=referencia,
        fecha=datetime.now(timezone.utc),
    )


def crear_consumo_interno(
    producto_id: int, cantidad: float, referencia: str, orden_id: int | None = None
) -> StockMovimiento:
    """Lo que otro proceso consumió de ese stock.

    Se guarda en negativo, igual que el CONSUMO de insumos, para que el
    disponible sea la suma directa del ledger y no una resta con signos
    repartidos entre tipos.
    """
    return StockMovimiento(
        producto_id=producto_id,
        tipo="CONSUMO_INTERNO",
        cantidad=-abs(cantidad),
        orden_id=orden_id,
        referencia=referencia,
        fecha=datetime.now(timezone.utc),
    )


async def disponible_de_articulo(session: AsyncSession, producto_id: int) -> float:
    total = (
        await session.execute(
            select(func.sum(StockMovimiento.cantidad)).where(StockMovimiento.producto_id == producto_id)
        )
    ).scalar_one_or_none()
    return float(total or 0)


async def disponible_de_articulos(session: AsyncSession, producto_ids: list[int]) -> dict[int, float]:
    if not producto_ids:
        return {}
    filas = (
        await session.execute(
            select(StockMovimiento.producto_id, func.sum(StockMovimiento.cantidad))
            .where(StockMovimiento.producto_id.in_(producto_ids))
            .group_by(StockMovimiento.producto_id)
        )
    ).all()
    return {producto_id: float(total or 0) for producto_id, total in filas}


async def comprometido_de_articulo(session: AsyncSession, producto_id: int) -> float:
    """Cuánto del consumo de ese artículo viene de órdenes que todavía no arrancaron.

    Ese consumo ya está restado del disponible; se expone aparte para que se vea
    cuánto del saldo restante está hablado. Devuelve 0 hasta que F4 conecte el
    consumo de semielaborados a la generación de órdenes (tarea 5.4).
    """
    total = (
        await session.execute(
            select(func.sum(StockMovimiento.cantidad))
            .join(OrdenProduccion, OrdenProduccion.id == StockMovimiento.orden_id)
            .where(
                StockMovimiento.producto_id == producto_id,
                StockMovimiento.tipo == "CONSUMO_INTERNO",
                OrdenProduccion.estado == "ASIGNADA",
            )
        )
    ).scalar_one_or_none()
    return abs(float(total or 0))


async def consumir_articulo(
    session: AsyncSession, producto_id: int, cantidad: float, referencia: str, orden_id: int | None = None
) -> StockMovimiento:
    """Consume stock de un artículo producido, sin dejarlo en negativo.

    Un semielaborado no se puede consumir de más: a diferencia de un insumo,
    donde el faltante físico puede taparse con una compra sin registrar, acá el
    saldo es exactamente lo que las órdenes anteriores fabricaron. Consumir más
    de lo que hay sería un error de cálculo, no un desfase de inventario.
    """
    disponible = await disponible_de_articulo(session, producto_id)
    if cantidad > disponible + 1e-9:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"No hay stock suficiente del artículo {producto_id}: "
                f"se piden {cantidad:g} y hay {disponible:g}"
            ),
        )
    movimiento = crear_consumo_interno(producto_id, cantidad, referencia, orden_id)
    session.add(movimiento)
    return movimiento


async def list_movimientos_articulo(session: AsyncSession, producto_id: int) -> list[StockMovimiento]:
    stmt = (
        select(StockMovimiento)
        .where(StockMovimiento.producto_id == producto_id)
        .order_by(StockMovimiento.fecha.desc(), StockMovimiento.id.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
