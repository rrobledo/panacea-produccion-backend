from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.models.proveedor import Proveedor
from app.schemas.proveedor import ProveedorCreate, ProveedorRead, ProveedorUpdate

router = APIRouter(prefix="/proveedores", tags=["proveedores"])


@router.get("", response_model=list[ProveedorRead])
async def list_proveedores(
    nombre: str | None = None,
    estado: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Proveedor).order_by(Proveedor.nombre)
    if nombre:
        stmt = stmt.where(Proveedor.nombre.ilike(f"%{nombre}%"))
    if estado and estado != "ALL":
        stmt = stmt.where(Proveedor.estado == estado)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ProveedorRead, status_code=status.HTTP_201_CREATED)
async def create_proveedor(payload: ProveedorCreate, session: AsyncSession = Depends(get_session)):
    existing = await session.execute(select(Proveedor).where(Proveedor.cuit == payload.cuit))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="cuit already exists")
    proveedor = Proveedor(**payload.model_dump(), fecha_alta=date.today())
    session.add(proveedor)
    await session.commit()
    await session.refresh(proveedor)
    return proveedor


@router.get("/{proveedor_id}", response_model=ProveedorRead)
async def get_proveedor(proveedor_id: int, session: AsyncSession = Depends(get_session)):
    proveedor = await session.get(Proveedor, proveedor_id)
    if proveedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor not found")
    return proveedor


@router.put("/{proveedor_id}", response_model=ProveedorRead)
async def update_proveedor(proveedor_id: int, payload: ProveedorUpdate, session: AsyncSession = Depends(get_session)):
    proveedor = await session.get(Proveedor, proveedor_id)
    if proveedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor not found")
    for field, value in payload.model_dump().items():
        setattr(proveedor, field, value)
    await session.commit()
    await session.refresh(proveedor)
    return proveedor


@router.delete("/{proveedor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proveedor(proveedor_id: int, session: AsyncSession = Depends(get_session)):
    proveedor = await session.get(Proveedor, proveedor_id)
    if proveedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor not found")
    await session.delete(proveedor)
    await session.commit()
