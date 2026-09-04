from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.models.insumos import Insumos
from app.schemas.insumos import InsumoCreate, InsumoRead, InsumoUpdate
from app.schemas.stock import AjusteStockCreate, StockMovimientoRead
from app.services import stock_service

router = APIRouter(prefix="/insumos", tags=["insumos"])


async def _get_insumo_or_404(session: AsyncSession, insumo_id: int) -> Insumos:
    insumo = await session.get(Insumos, insumo_id)
    if insumo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insumo not found")
    return insumo


@router.get("", response_model=list[InsumoRead])
async def list_insumos(
    nombre: str | None = None,
    q: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    busqueda = nombre or q
    stmt = select(Insumos).order_by(Insumos.nombre)
    if busqueda:
        stmt = stmt.where(Insumos.nombre.ilike(f"%{busqueda}%"))
    result = await session.execute(stmt)
    insumos = result.scalars().all()
    comprometido_map = await stock_service.get_comprometido_map(session, [i.id for i in insumos])
    return [InsumoRead.from_orm_row(i, comprometido_map.get(i.id, 0)) for i in insumos]


@router.post("", response_model=InsumoRead, status_code=status.HTTP_201_CREATED)
async def create_insumo(payload: InsumoCreate, session: AsyncSession = Depends(get_session)):
    insumo = Insumos(**payload.model_dump())
    session.add(insumo)
    await session.flush()
    if insumo.cantidad:
        # La cantidad de apertura ya viene seteada arriba (Insumos(**payload));
        # esto solo deja el rastro en el ledger, sin volver a sumar el delta.
        stock_service.registrar_apertura(session, insumo, insumo.cantidad)
    await session.commit()
    await session.refresh(insumo)
    return InsumoRead.from_orm_row(insumo)


@router.get("/{insumo_id}", response_model=InsumoRead)
async def get_insumo(insumo_id: int, session: AsyncSession = Depends(get_session)):
    insumo = await _get_insumo_or_404(session, insumo_id)
    comprometido_map = await stock_service.get_comprometido_map(session, [insumo_id])
    return InsumoRead.from_orm_row(insumo, comprometido_map.get(insumo_id, 0))


@router.put("/{insumo_id}", response_model=InsumoRead)
async def update_insumo(insumo_id: int, payload: InsumoUpdate, session: AsyncSession = Depends(get_session)):
    insumo = await _get_insumo_or_404(session, insumo_id)
    for field, value in payload.model_dump().items():
        setattr(insumo, field, value)
    await session.commit()
    await session.refresh(insumo)
    comprometido_map = await stock_service.get_comprometido_map(session, [insumo_id])
    return InsumoRead.from_orm_row(insumo, comprometido_map.get(insumo_id, 0))


@router.delete("/{insumo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_insumo(insumo_id: int, session: AsyncSession = Depends(get_session)):
    insumo = await _get_insumo_or_404(session, insumo_id)
    await session.delete(insumo)
    await session.commit()


@router.get("/{insumo_id}/movimientos", response_model=list[StockMovimientoRead])
async def list_movimientos(insumo_id: int, session: AsyncSession = Depends(get_session)):
    await _get_insumo_or_404(session, insumo_id)
    return await stock_service.list_movimientos(session, insumo_id)


@router.post("/{insumo_id}/movimientos", response_model=StockMovimientoRead, status_code=status.HTTP_201_CREATED)
async def ajustar_stock(insumo_id: int, payload: AjusteStockCreate, session: AsyncSession = Depends(get_session)):
    insumo = await _get_insumo_or_404(session, insumo_id)
    return await stock_service.crear_ajuste(session, insumo, payload.cantidad, payload.motivo)
