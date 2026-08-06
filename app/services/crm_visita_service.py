from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_contacto import CrmContacto
from app.models.crm_vendedor import CrmVendedor
from app.models.crm_visita import CrmVisita
from app.schemas.crm_visita import CrmVisitaCreate
from app.services import crm_auditoria_service


async def list_visitas(session: AsyncSession, contacto_id: int | None = None) -> list[CrmVisita]:
    stmt = select(CrmVisita).order_by(CrmVisita.fecha.desc())
    if contacto_id is not None:
        stmt = stmt.where(CrmVisita.contacto_id == contacto_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_visita(session: AsyncSession, visita_id: int) -> CrmVisita:
    visita = await session.get(CrmVisita, visita_id)
    if visita is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visita not found")
    return visita


async def create_visita(session: AsyncSession, payload: CrmVisitaCreate, usuario_id: int | None) -> CrmVisita:
    if await session.get(CrmContacto, payload.contacto_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contacto_id does not reference an existing row")
    if await session.get(CrmVendedor, payload.vendedor_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="vendedor_id does not reference an existing row")

    visita = CrmVisita(**payload.model_dump())
    session.add(visita)
    await session.flush()
    await crm_auditoria_service.log_create(session, "Visita", visita.id, usuario_id)
    await session.commit()
    await session.refresh(visita)
    return visita
