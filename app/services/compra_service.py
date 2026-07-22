from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer

from app.models.compra import Compra, CompraAdjunto, CompraDetalle, CompraImpuesto
from app.models.insumos import Insumos
from app.models.item_gasto import ItemGasto
from app.models.proveedor import Proveedor
from app.schemas.compra import CompraCreate, CompraDetalleCreate, CompraImpuestoCreate, CompraUpdate
from app.services import movimiento_cc_service, orden_compra_service

IVA_TIPOS = {"IVA_21", "IVA_10_5", "IVA_27"}
RETENCION_TIPOS = {"RETENCION_IVA", "RETENCION_GANANCIAS", "RETENCION_SUSS"}


async def _resolve_descripcion(session: AsyncSession, item: CompraDetalleCreate) -> str:
    if item.tipo == "INSUMO":
        insumo = await session.get(Insumos, item.insumo_id)
        if insumo is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insumo not found")
        return item.descripcion or insumo.nombre
    if item.tipo == "ITEM_GASTO":
        item_gasto = await session.get(ItemGasto, item.item_gasto_id)
        if item_gasto is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ItemGasto not found")
        return item.descripcion or item_gasto.nombre
    return item.descripcion


async def _build_detalle_row(session: AsyncSession, compra_id: int, item: CompraDetalleCreate) -> CompraDetalle:
    descripcion = await _resolve_descripcion(session, item)
    importe_neto = item.cantidad * item.precio_unitario - item.descuento
    importe_iva = importe_neto * item.alicuota_iva / 100
    return CompraDetalle(
        compra_id=compra_id,
        tipo=item.tipo,
        insumo_id=item.insumo_id,
        item_gasto_id=item.item_gasto_id,
        descripcion=descripcion,
        cantidad=item.cantidad,
        precio_unitario=item.precio_unitario,
        descuento=item.descuento,
        alicuota_iva=item.alicuota_iva,
        importe_neto=importe_neto,
        importe_iva=importe_iva,
        importe_total=importe_neto + importe_iva,
        centro_costo_id=item.centro_costo_id,
        cuenta_contable_id=item.cuenta_contable_id,
    )


def _build_impuesto_row(compra_id: int, item: CompraImpuestoCreate) -> CompraImpuesto:
    return CompraImpuesto(
        compra_id=compra_id,
        tipo=item.tipo,
        base_imponible=item.base_imponible,
        porcentaje=item.porcentaje,
        importe=item.importe,
    )


def _compute_totals(detalle: list[CompraDetalle], impuestos: list[CompraImpuesto]) -> dict[str, float]:
    subtotal = sum(d.importe_neto for d in detalle)
    iva = sum(d.importe_iva for d in detalle) + sum(i.importe for i in impuestos if i.tipo in IVA_TIPOS)
    percepciones = sum(i.importe for i in impuestos if i.tipo.startswith("PERCEPCION_"))
    # Retenciones sufridas are withheld at payment time (Tesorería), not
    # added to the comprobante's own total — kept on CompraImpuesto for
    # reporting only, excluded here.
    otros_impuestos = sum(
        i.importe
        for i in impuestos
        if i.tipo not in IVA_TIPOS and i.tipo not in RETENCION_TIPOS and not i.tipo.startswith("PERCEPCION_")
    )
    total = subtotal + iva + percepciones + otros_impuestos
    return {
        "subtotal": subtotal,
        "iva": iva,
        "percepciones": percepciones,
        "impuestos": otros_impuestos,
        "total": total,
    }


def _apply_totals(compra: Compra, totals: dict[str, float]) -> None:
    compra.subtotal = totals["subtotal"]
    compra.iva = totals["iva"]
    compra.percepciones = totals["percepciones"]
    compra.impuestos = totals["impuestos"]
    compra.total = totals["total"]
    # Only re-base saldo_pendiente while nothing has been paid yet — once a
    # pago has been applied (estado moves off PENDIENTE), leave the
    # trigger-maintained balance alone.
    if compra.condicion_pago == "CUENTA_CORRIENTE" and compra.estado == "PENDIENTE":
        compra.saldo_pendiente = compra.total


async def _get_proveedor_or_404(session: AsyncSession, proveedor_id: int) -> Proveedor:
    proveedor = await session.get(Proveedor, proveedor_id)
    if proveedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor not found")
    return proveedor


async def create_compra(session: AsyncSession, payload: CompraCreate) -> Compra:
    proveedor = await _get_proveedor_or_404(session, payload.proveedor_id)
    condicion_pago = payload.condicion_pago or proveedor.condicion_pago

    compra = Compra(
        proveedor_id=payload.proveedor_id,
        orden_compra_id=payload.orden_compra_id,
        tipo_comprobante=payload.tipo_comprobante,
        punto_venta=payload.punto_venta,
        numero=payload.numero,
        fecha=payload.fecha,
        fecha_vencimiento=payload.fecha_vencimiento,
        condicion_pago=condicion_pago,
        categoria=payload.categoria,
        observaciones=payload.observaciones,
    )
    session.add(compra)
    await session.flush()

    detalle_rows = [await _build_detalle_row(session, compra.id, item) for item in payload.detalle]
    impuesto_rows = [_build_impuesto_row(compra.id, item) for item in payload.impuestos]
    session.add_all(detalle_rows)
    session.add_all(impuesto_rows)

    totals = _compute_totals(detalle_rows, impuesto_rows)
    compra.subtotal = totals["subtotal"]
    compra.iva = totals["iva"]
    compra.percepciones = totals["percepciones"]
    compra.impuestos = totals["impuestos"]
    compra.total = totals["total"]

    if condicion_pago == "CONTADO":
        compra.saldo_pendiente = 0
        compra.estado = "PAGADO"
    else:
        compra.saldo_pendiente = compra.total
        compra.estado = "PENDIENTE"

    await movimiento_cc_service.append_compra_movimiento(session, compra)

    if payload.orden_compra_id is not None:
        await orden_compra_service.register_reception(session, payload.orden_compra_id, detalle_rows)

    await session.commit()
    return await get_compra(session, compra.id, with_detail=True)


async def update_compra(session: AsyncSession, compra_id: int, payload: CompraUpdate) -> Compra:
    compra = await get_compra(session, compra_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(compra, field, value)
    await session.commit()
    return await get_compra(session, compra_id, with_detail=True)


async def delete_compra(session: AsyncSession, compra_id: int) -> None:
    compra = await get_compra(session, compra_id)
    await session.delete(compra)
    await session.commit()


async def get_compra(session: AsyncSession, compra_id: int, with_detail: bool = False) -> Compra:
    if with_detail:
        stmt = (
            select(Compra)
            .options(
                selectinload(Compra.detalle),
                selectinload(Compra.impuestos_detalle),
                selectinload(Compra.adjuntos),
            )
            .where(Compra.id == compra_id)
            # Same rationale as cuenta_corriente_service.get_cuenta_corriente:
            # avoid returning a stale identity-mapped row after the
            # PagoAplicacion trigger updated saldo_pendiente/estado
            # out-of-band.
            .execution_options(populate_existing=True)
        )
        row = (await session.execute(stmt)).unique().scalar_one_or_none()
    else:
        row = await session.get(Compra, compra_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra not found")
    return row


async def list_compras(
    session: AsyncSession,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    estado: str | None = None,
    proveedor_id: int | None = None,
    con_saldo: bool | None = None,
    categoria: str | None = None,
) -> list[Compra]:
    stmt = select(Compra).order_by(Compra.created_at.desc(), Compra.id.desc())
    if fecha_desde is not None:
        stmt = stmt.where(Compra.fecha >= fecha_desde)
    if fecha_hasta is not None:
        stmt = stmt.where(Compra.fecha <= fecha_hasta)
    if estado is not None and estado != "TODOS":
        stmt = stmt.where(Compra.estado == estado)
    if proveedor_id is not None:
        stmt = stmt.where(Compra.proveedor_id == proveedor_id)
    if con_saldo is not None:
        stmt = stmt.where(Compra.saldo_pendiente > 1 if con_saldo else Compra.saldo_pendiente <= 0)
    if categoria is not None:
        stmt = stmt.where(Compra.categoria == categoria)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def add_detalle(session: AsyncSession, compra_id: int, items: list[CompraDetalleCreate]) -> Compra:
    compra = await get_compra(session, compra_id, with_detail=True)
    new_rows = [await _build_detalle_row(session, compra_id, item) for item in items]
    session.add_all(new_rows)
    await session.flush()
    totals = _compute_totals(list(compra.detalle) + new_rows, list(compra.impuestos_detalle))
    _apply_totals(compra, totals)
    await session.commit()
    return await get_compra(session, compra_id, with_detail=True)


async def add_impuestos(session: AsyncSession, compra_id: int, items: list[CompraImpuestoCreate]) -> Compra:
    compra = await get_compra(session, compra_id, with_detail=True)
    new_rows = [_build_impuesto_row(compra_id, item) for item in items]
    session.add_all(new_rows)
    await session.flush()
    totals = _compute_totals(list(compra.detalle), list(compra.impuestos_detalle) + new_rows)
    _apply_totals(compra, totals)
    await session.commit()
    return await get_compra(session, compra_id, with_detail=True)


async def add_adjunto(
    session: AsyncSession,
    compra_id: int,
    filename: str,
    content: bytes,
    content_type: str | None,
) -> CompraAdjunto:
    await get_compra(session, compra_id)  # 404 if missing
    row = CompraAdjunto(compra_id=compra_id, nombre=filename, contenido=content, tipo=content_type)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_adjunto(session: AsyncSession, compra_id: int, adjunto_id: int) -> CompraAdjunto:
    stmt = (
        select(CompraAdjunto)
        .options(undefer(CompraAdjunto.contenido))
        .where(CompraAdjunto.id == adjunto_id, CompraAdjunto.compra_id == compra_id)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Adjunto not found")
    return row
