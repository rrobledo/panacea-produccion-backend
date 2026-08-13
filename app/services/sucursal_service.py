from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sucursal import Sucursal
from app.schemas.sucursal import SucursalCreate, SucursalUpdate


async def create_sucursal(session: AsyncSession, payload: SucursalCreate) -> Sucursal:
    sucursal = Sucursal(**payload.model_dump())
    session.add(sucursal)
    await session.commit()
    await session.refresh(sucursal)
    return sucursal


async def list_sucursales(
    session: AsyncSession, tipo: str | None = None, activa: bool | None = None
) -> list[Sucursal]:
    stmt = select(Sucursal).order_by(Sucursal.nombre)
    if tipo is not None:
        stmt = stmt.where(Sucursal.tipo == tipo)
    if activa is not None:
        stmt = stmt.where(Sucursal.activa == activa)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_sucursal(session: AsyncSession, sucursal_id: int) -> Sucursal:
    sucursal = await session.get(Sucursal, sucursal_id)
    if sucursal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal not found")
    return sucursal


async def update_sucursal(session: AsyncSession, sucursal: Sucursal, payload: SucursalUpdate) -> Sucursal:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sucursal, field, value)
    await session.commit()
    await session.refresh(sucursal)
    return sucursal
