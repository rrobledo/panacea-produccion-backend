from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cuenta_corriente import (
    CuentaCorrienteProveedor,
    CuentaCorrienteProveedorAfect,
    CuentaCorrienteProveedorDetalle,
)
from app.schemas.cuenta_corriente import (
    CuentaCorrienteProveedorCreate,
    CuentaCorrienteProveedorUpdate,
    DetalleInsumoCreate,
)

INMEDIATE_PAYMENT_TIPOS_PAGO = {"EFECTIVO", "TRANSFERENCIA"}
IMAGE_FIELDS = ["image", "image2", "content_type"]


def _add_detalle_rows(session: AsyncSession, cuenta_corriente_id: int, insumos: list[DetalleInsumoCreate]) -> None:
    for item in insumos:
        session.add(
            CuentaCorrienteProveedorDetalle(
                cuentacorrienteproveedor_id=cuenta_corriente_id,
                insumo_id=item.insumo,
                cantidad=item.cantidad,
                subtotal=item.subtotal,
            )
        )


async def create_cuenta_corriente(
    session: AsyncSession, payload: CuentaCorrienteProveedorCreate
) -> CuentaCorrienteProveedor:
    data = payload.model_dump(exclude={"factura_id", "insumos"})
    data["proveedor_id"] = data.pop("proveedor")

    if payload.tipo_movimiento == "PAGO":
        if not payload.factura_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="factura_id is required when tipo_movimiento=PAGO",
            )
        data["importe_pendiente"] = data["importe_total"]
        row = CuentaCorrienteProveedor(**data)
        session.add(row)
        await session.flush()

        # The DB trigger trg_update_importe_pendiente (on INSERT into
        # costos_cuentacorrienteproveedorafect) is what actually decrements
        # importe_pendiente / recomputes estado on both the factura and the
        # pago rows below — do not replicate that arithmetic here, or it
        # will be double-applied.
        session.add(
            CuentaCorrienteProveedorAfect(
                factura_id=payload.factura_id,
                pago_id=row.id,
                importe=row.importe_total,
            )
        )
    else:
        if payload.tipo_pago in INMEDIATE_PAYMENT_TIPOS_PAGO:
            data["estado"] = "PAGADO"
            data["importe_pendiente"] = 0
        else:
            data["importe_pendiente"] = data["importe_total"]

        row = CuentaCorrienteProveedor(**data)
        session.add(row)
        await session.flush()

    if payload.insumos:
        _add_detalle_rows(session, row.id, payload.insumos)

    await session.commit()
    return await get_cuenta_corriente(session, row.id, with_detail=True)


async def update_cuenta_corriente(
    session: AsyncSession, row: CuentaCorrienteProveedor, payload: CuentaCorrienteProveedorUpdate
) -> CuentaCorrienteProveedor:
    data = payload.model_dump(exclude={"factura_id", "insumos"}, exclude_unset=True)
    if "proveedor" in data:
        data["proveedor_id"] = data.pop("proveedor")
    for field, value in data.items():
        setattr(row, field, value)
    if payload.tipo_pago in INMEDIATE_PAYMENT_TIPOS_PAGO:
        row.estado = "PAGADO"
    await session.commit()
    return await get_cuenta_corriente(session, row.id, with_detail=True)


async def get_cuenta_corriente(
    session: AsyncSession, entry_id: int, with_detail: bool = False
) -> CuentaCorrienteProveedor:
    if with_detail:
        stmt = (
            select(CuentaCorrienteProveedor)
            .options(
                selectinload(CuentaCorrienteProveedor.detalle).selectinload(
                    CuentaCorrienteProveedorDetalle.insumo
                )
            )
            .where(CuentaCorrienteProveedor.id == entry_id)
            # Without this, an already-loaded object of this identity (e.g.
            # one we just inserted in this same session) is returned as-is
            # from SQLAlchemy's identity map, silently ignoring DB-side
            # changes made by the importe_pendiente/estado trigger.
            .execution_options(populate_existing=True)
        )
        row = (await session.execute(stmt)).unique().scalar_one_or_none()
        if row is not None:
            await session.refresh(row, attribute_names=IMAGE_FIELDS)
    else:
        row = await session.get(CuentaCorrienteProveedor, entry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CuentaCorrienteProveedor not found")
    return row


async def list_pagos_for_factura(session: AsyncSession, factura_id: int) -> list[CuentaCorrienteProveedor]:
    await get_cuenta_corriente(session, factura_id)
    stmt = (
        select(CuentaCorrienteProveedor)
        .join(
            CuentaCorrienteProveedorAfect,
            CuentaCorrienteProveedorAfect.pago_id == CuentaCorrienteProveedor.id,
        )
        .where(CuentaCorrienteProveedorAfect.factura_id == factura_id)
        .order_by(CuentaCorrienteProveedor.fecha_emision)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_detalle(session: AsyncSession, cuenta_corriente_id: int) -> list[CuentaCorrienteProveedorDetalle]:
    await get_cuenta_corriente(session, cuenta_corriente_id)
    stmt = (
        select(CuentaCorrienteProveedorDetalle)
        .where(CuentaCorrienteProveedorDetalle.cuentacorrienteproveedor_id == cuenta_corriente_id)
        .order_by(CuentaCorrienteProveedorDetalle.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def add_detalle(
    session: AsyncSession, cuenta_corriente_id: int, items: list[DetalleInsumoCreate]
) -> list[CuentaCorrienteProveedorDetalle]:
    await get_cuenta_corriente(session, cuenta_corriente_id)
    rows = [
        CuentaCorrienteProveedorDetalle(
            cuentacorrienteproveedor_id=cuenta_corriente_id,
            insumo_id=item.insumo,
            cantidad=item.cantidad,
            subtotal=item.subtotal,
        )
        for item in items
    ]
    session.add_all(rows)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return rows


async def delete_detalle(session: AsyncSession, cuenta_corriente_id: int, detalle_id: int) -> None:
    stmt = select(CuentaCorrienteProveedorDetalle).where(
        CuentaCorrienteProveedorDetalle.id == detalle_id,
        CuentaCorrienteProveedorDetalle.cuentacorrienteproveedor_id == cuenta_corriente_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detalle not found")
    await session.delete(row)
    await session.commit()
