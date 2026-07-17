from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.models.item_gasto import ItemGasto
from app.schemas.item_gasto import ItemGastoCreate, ItemGastoRead

router = APIRouter(prefix="/items-gasto", tags=["items-gasto"])


@router.get("", response_model=list[ItemGastoRead])
async def list_items_gasto(nombre: str | None = None, session: AsyncSession = Depends(get_session)):
    stmt = select(ItemGasto).order_by(ItemGasto.nombre)
    if nombre:
        stmt = stmt.where(ItemGasto.nombre.ilike(f"%{nombre}%"))
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ItemGastoRead, status_code=status.HTTP_201_CREATED)
async def create_item_gasto(payload: ItemGastoCreate, session: AsyncSession = Depends(get_session)):
    item_gasto = ItemGasto(**payload.model_dump())
    session.add(item_gasto)
    await session.commit()
    await session.refresh(item_gasto)
    return item_gasto


@router.get("/{item_gasto_id}", response_model=ItemGastoRead)
async def get_item_gasto(item_gasto_id: int, session: AsyncSession = Depends(get_session)):
    item_gasto = await session.get(ItemGasto, item_gasto_id)
    if item_gasto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ItemGasto not found")
    return item_gasto


@router.put("/{item_gasto_id}", response_model=ItemGastoRead)
async def update_item_gasto(item_gasto_id: int, payload: ItemGastoCreate, session: AsyncSession = Depends(get_session)):
    item_gasto = await session.get(ItemGasto, item_gasto_id)
    if item_gasto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ItemGasto not found")
    for field, value in payload.model_dump().items():
        setattr(item_gasto, field, value)
    await session.commit()
    await session.refresh(item_gasto)
    return item_gasto


@router.delete("/{item_gasto_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item_gasto(item_gasto_id: int, session: AsyncSession = Depends(get_session)):
    item_gasto = await session.get(ItemGasto, item_gasto_id)
    if item_gasto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ItemGasto not found")
    await session.delete(item_gasto)
    await session.commit()
