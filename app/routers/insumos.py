from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.models.insumos import Insumos
from app.schemas.insumos import InsumoCreate, InsumoRead

router = APIRouter(prefix="/insumos", tags=["insumos"])


@router.get("", response_model=list[InsumoRead])
async def list_insumos(nombre: str | None = None, session: AsyncSession = Depends(get_session)):
    stmt = select(Insumos).order_by(Insumos.nombre)
    if nombre:
        stmt = stmt.where(Insumos.nombre.ilike(f"%{nombre}%"))
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=InsumoRead, status_code=status.HTTP_201_CREATED)
async def create_insumo(payload: InsumoCreate, session: AsyncSession = Depends(get_session)):
    insumo = Insumos(**payload.model_dump())
    session.add(insumo)
    await session.commit()
    await session.refresh(insumo)
    return insumo


@router.get("/{insumo_id}", response_model=InsumoRead)
async def get_insumo(insumo_id: int, session: AsyncSession = Depends(get_session)):
    insumo = await session.get(Insumos, insumo_id)
    if insumo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insumo not found")
    return insumo


@router.put("/{insumo_id}", response_model=InsumoRead)
async def update_insumo(insumo_id: int, payload: InsumoCreate, session: AsyncSession = Depends(get_session)):
    insumo = await session.get(Insumos, insumo_id)
    if insumo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insumo not found")
    for field, value in payload.model_dump().items():
        setattr(insumo, field, value)
    await session.commit()
    await session.refresh(insumo)
    return insumo


@router.delete("/{insumo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_insumo(insumo_id: int, session: AsyncSession = Depends(get_session)):
    insumo = await session.get(Insumos, insumo_id)
    if insumo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insumo not found")
    await session.delete(insumo)
    await session.commit()
