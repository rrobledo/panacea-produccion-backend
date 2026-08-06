from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_campana import CrmCampana, CrmContactoCampana
from app.models.crm_contacto import CrmContacto
from app.schemas.crm_campana import CrmCampanaConversion, CrmCampanaCreate, CrmCampanaUpdate


async def list_campanas(session: AsyncSession) -> list[CrmCampana]:
    result = await session.execute(select(CrmCampana).order_by(CrmCampana.fecha_inicio.desc()))
    return list(result.scalars().all())


async def get_campana(session: AsyncSession, campana_id: int) -> CrmCampana:
    campana = await session.get(CrmCampana, campana_id)
    if campana is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaña not found")
    return campana


async def create_campana(session: AsyncSession, payload: CrmCampanaCreate) -> CrmCampana:
    campana = CrmCampana(**payload.model_dump())
    session.add(campana)
    await session.commit()
    await session.refresh(campana)
    return campana


async def update_campana(session: AsyncSession, campana_id: int, payload: CrmCampanaUpdate) -> CrmCampana:
    campana = await get_campana(session, campana_id)
    for field, value in payload.model_dump().items():
        setattr(campana, field, value)
    await session.commit()
    await session.refresh(campana)
    return campana


async def associate_contacto(session: AsyncSession, campana_id: int, contacto_id: int) -> CrmContactoCampana:
    await get_campana(session, campana_id)
    if await session.get(CrmContacto, contacto_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto not found")

    existing = await session.execute(
        select(CrmContactoCampana).where(
            CrmContactoCampana.campana_id == campana_id, CrmContactoCampana.contacto_id == contacto_id
        )
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        return row

    row = CrmContactoCampana(campana_id=campana_id, contacto_id=contacto_id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_conversion(session: AsyncSession, campana_id: int) -> CrmCampanaConversion:
    await get_campana(session, campana_id)
    stmt = (
        select(func.count(CrmContactoCampana.id), func.count(CrmContacto.erp_cliente_id))
        .select_from(CrmContactoCampana)
        .join(CrmContacto, CrmContacto.id == CrmContactoCampana.contacto_id)
        .where(CrmContactoCampana.campana_id == campana_id)
    )
    total, con_erp = (await session.execute(stmt)).one()
    return CrmCampanaConversion(campana_id=campana_id, contactos_asociados=total, contactos_con_erp=con_erp)
