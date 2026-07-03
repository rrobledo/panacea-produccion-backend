from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_api_key
from app.models.cuenta_corriente import CuentaCorrienteProveedor
from app.schemas.cuenta_corriente import (
    CuentaCorrienteProveedorCreate,
    CuentaCorrienteProveedorDetailRead,
    CuentaCorrienteProveedorRead,
    CuentaCorrienteProveedorUpdate,
    DetalleInsumoCreate,
    DetalleInsumoRead,
)
from app.services import cuenta_corriente_service as service

router = APIRouter(prefix="/ctacteprov", tags=["cuenta-corriente-proveedor"])
resumen_router = APIRouter(tags=["cuenta-corriente-proveedor"])


@router.get("", response_model=list[CuentaCorrienteProveedorRead])
async def list_cuenta_corriente(
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    estado: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(CuentaCorrienteProveedor).order_by(CuentaCorrienteProveedor.fecha_emision)
    if fecha_desde is not None:
        stmt = stmt.where(CuentaCorrienteProveedor.fecha_emision >= fecha_desde)
    if fecha_hasta is not None:
        stmt = stmt.where(CuentaCorrienteProveedor.fecha_emision <= fecha_hasta)
    if estado is not None and estado != "TODOS":
        stmt = stmt.where(CuentaCorrienteProveedor.estado == estado)
    result = await session.execute(stmt)
    return [CuentaCorrienteProveedorRead.from_orm_row(row) for row in result.scalars().all()]


@router.post(
    "",
    response_model=CuentaCorrienteProveedorDetailRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
async def create_cuenta_corriente(
    payload: CuentaCorrienteProveedorCreate, session: AsyncSession = Depends(get_session)
):
    row = await service.create_cuenta_corriente(session, payload)
    return CuentaCorrienteProveedorDetailRead.from_orm_row(row)


@router.get("/{entry_id}", response_model=CuentaCorrienteProveedorDetailRead)
async def get_cuenta_corriente(entry_id: int, session: AsyncSession = Depends(get_session)):
    row = await service.get_cuenta_corriente(session, entry_id, with_detail=True)
    return CuentaCorrienteProveedorDetailRead.from_orm_row(row)


@router.put(
    "/{entry_id}", response_model=CuentaCorrienteProveedorDetailRead, dependencies=[Depends(require_api_key)]
)
async def update_cuenta_corriente(
    entry_id: int, payload: CuentaCorrienteProveedorUpdate, session: AsyncSession = Depends(get_session)
):
    row = await service.get_cuenta_corriente(session, entry_id)
    row = await service.update_cuenta_corriente(session, row, payload)
    return CuentaCorrienteProveedorDetailRead.from_orm_row(row)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
async def delete_cuenta_corriente(entry_id: int, session: AsyncSession = Depends(get_session)):
    row = await service.get_cuenta_corriente(session, entry_id)
    await session.delete(row)
    await session.commit()


@router.get("/{factura_id}/pagos", response_model=list[CuentaCorrienteProveedorRead])
async def list_pagos(factura_id: int, session: AsyncSession = Depends(get_session)):
    rows = await service.list_pagos_for_factura(session, factura_id)
    return [CuentaCorrienteProveedorRead.from_orm_row(row) for row in rows]


@router.get("/{entry_id}/insumos", response_model=list[DetalleInsumoRead])
async def list_insumos_detalle(entry_id: int, session: AsyncSession = Depends(get_session)):
    rows = await service.list_detalle(session, entry_id)
    return [DetalleInsumoRead.from_orm_row(row) for row in rows]


@router.post(
    "/{entry_id}/insumos",
    response_model=list[DetalleInsumoRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
async def add_insumos_detalle(
    entry_id: int,
    payload: DetalleInsumoCreate | list[DetalleInsumoCreate],
    session: AsyncSession = Depends(get_session),
):
    items = payload if isinstance(payload, list) else [payload]
    rows = await service.add_detalle(session, entry_id, items)
    return [DetalleInsumoRead.from_orm_row(row) for row in rows]


@router.delete(
    "/{entry_id}/insumos/{detalle_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_api_key)],
)
async def delete_insumo_detalle(entry_id: int, detalle_id: int, session: AsyncSession = Depends(get_session)):
    await service.delete_detalle(session, entry_id, detalle_id)


@resumen_router.get("/ctacteprovresumen")
async def get_cuenta_corriente_resumen(
    fecha_desde: date,
    fecha_hasta: date,
    session: AsyncSession = Depends(get_session),
):
    if fecha_desde > fecha_hasta:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="fecha_desde must be <= fecha_hasta")

    stmt = text(
        """
        with t_total_facturas_pendientes as (
            select round(sum(importe_pendiente)::numeric, 2) as total_facturas_pendientes
              from costos_cuentacorrienteproveedor
             where tipo_movimiento = 'FACTURA'
               and tipo_pago = 'CUENTA_CORRIENTE'
        ),
        t_total_gastos as (
            select round(sum(importe_total)::numeric, 2) as total_gastos
              from costos_cuentacorrienteproveedor
             where fecha_emision between :fecha_desde and :fecha_hasta
               and (
                    (tipo_movimiento = 'FACTURA' and tipo_pago <> 'CUENTA_CORRIENTE')
                    or (tipo_movimiento = 'PAGO')
                   )
        )
        select
            (select total_facturas_pendientes from t_total_facturas_pendientes) as total_facturas_pendientes,
            (select total_gastos from t_total_gastos) as total_gastos
        """
    )
    result = await session.execute(stmt, {"fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta})
    row = result.mappings().one()
    return {
        "total_facturas_pendientes": float(row["total_facturas_pendientes"] or 0),
        "total_gastos": float(row["total_gastos"] or 0),
    }
