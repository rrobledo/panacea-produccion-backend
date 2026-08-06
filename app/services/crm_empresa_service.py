from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_empresa import CrmEmpresa
from app.schemas.crm_empresa import CrmEmpresaCreate, CrmEmpresaUpdate


async def list_empresas(session: AsyncSession, q: str | None = None) -> list[CrmEmpresa]:
    stmt = select(CrmEmpresa).order_by(CrmEmpresa.nombre)
    if q:
        stmt = stmt.where(CrmEmpresa.nombre.ilike(f"%{q}%"))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_empresa(session: AsyncSession, empresa_id: int) -> CrmEmpresa:
    empresa = await session.get(CrmEmpresa, empresa_id)
    if empresa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa not found")
    return empresa


async def create_empresa(session: AsyncSession, payload: CrmEmpresaCreate) -> CrmEmpresa:
    empresa = CrmEmpresa(**payload.model_dump())
    session.add(empresa)
    await session.commit()
    await session.refresh(empresa)
    return empresa


async def update_empresa(session: AsyncSession, empresa_id: int, payload: CrmEmpresaUpdate) -> CrmEmpresa:
    empresa = await get_empresa(session, empresa_id)
    for field, value in payload.model_dump().items():
        setattr(empresa, field, value)
    await session.commit()
    await session.refresh(empresa)
    return empresa
