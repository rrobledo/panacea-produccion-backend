from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_vendedor import CrmVendedor
from app.schemas.crm_vendedor import CrmVendedorCreate, CrmVendedorUpdate


async def list_vendedores(session: AsyncSession) -> list[CrmVendedor]:
    result = await session.execute(select(CrmVendedor).order_by(CrmVendedor.nombre))
    return list(result.scalars().all())


async def get_vendedor(session: AsyncSession, vendedor_id: int) -> CrmVendedor:
    vendedor = await session.get(CrmVendedor, vendedor_id)
    if vendedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendedor not found")
    return vendedor


async def create_vendedor(session: AsyncSession, payload: CrmVendedorCreate) -> CrmVendedor:
    vendedor = CrmVendedor(**payload.model_dump())
    session.add(vendedor)
    await session.commit()
    await session.refresh(vendedor)
    return vendedor


async def update_vendedor(session: AsyncSession, vendedor_id: int, payload: CrmVendedorUpdate) -> CrmVendedor:
    vendedor = await get_vendedor(session, vendedor_id)
    for field, value in payload.model_dump().items():
        setattr(vendedor, field, value)
    await session.commit()
    await session.refresh(vendedor)
    return vendedor
