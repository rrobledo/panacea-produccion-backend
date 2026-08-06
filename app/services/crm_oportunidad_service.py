from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.crm_contacto import CrmContacto
from app.models.crm_oportunidad import CrmActividad, CrmEtapaVenta, CrmOportunidad
from app.models.crm_visita import CrmVisita
from app.schemas.crm_oportunidad import CrmActividadCreate, CrmOportunidadCreate
from app.services import crm_auditoria_service

ETAPA_PRIMERA_COMPRA = "Primera Compra"


async def _get_etapa_by_nombre(session: AsyncSession, nombre: str) -> CrmEtapaVenta:
    result = await session.execute(select(CrmEtapaVenta).where(CrmEtapaVenta.nombre == nombre))
    etapa = result.scalar_one_or_none()
    if etapa is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown etapa '{nombre}'")
    return etapa


async def _has_erp_purchase(session: AsyncSession, erp_cliente_id: int) -> bool:
    result = await session.execute(
        text("SELECT 1 FROM panacea_sales_v2 WHERE customer_id = :cid LIMIT 1"), {"cid": erp_cliente_id}
    )
    return result.first() is not None


async def get_oportunidad(session: AsyncSession, oportunidad_id: int) -> CrmOportunidad:
    stmt = (
        select(CrmOportunidad)
        .options(selectinload(CrmOportunidad.etapa))
        .where(CrmOportunidad.id == oportunidad_id)
        .execution_options(populate_existing=True)
    )
    oportunidad = (await session.execute(stmt)).scalar_one_or_none()
    if oportunidad is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Oportunidad not found")
    return oportunidad


async def list_oportunidades(session: AsyncSession, contacto_id: int | None = None) -> list[CrmOportunidad]:
    stmt = select(CrmOportunidad).options(selectinload(CrmOportunidad.etapa)).order_by(CrmOportunidad.created_at.desc())
    if contacto_id is not None:
        stmt = stmt.where(CrmOportunidad.contacto_id == contacto_id)
    stmt = stmt.execution_options(populate_existing=True)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_oportunidad(
    session: AsyncSession, payload: CrmOportunidadCreate, usuario_id: int | None
) -> CrmOportunidad:
    if await session.get(CrmContacto, payload.contacto_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contacto_id does not reference an existing row")
    if payload.visita_id is not None and await session.get(CrmVisita, payload.visita_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="visita_id does not reference an existing row")

    etapa_lead = await _get_etapa_by_nombre(session, "Lead")
    oportunidad = CrmOportunidad(contacto_id=payload.contacto_id, visita_id=payload.visita_id, etapa_id=etapa_lead.id)
    session.add(oportunidad)
    await session.flush()
    await crm_auditoria_service.log_create(session, "Oportunidad", oportunidad.id, usuario_id)
    await session.commit()
    return await get_oportunidad(session, oportunidad.id)


async def update_etapa(
    session: AsyncSession, oportunidad_id: int, etapa_nombre: str, usuario_id: int | None
) -> CrmOportunidad:
    oportunidad = await get_oportunidad(session, oportunidad_id)
    nueva_etapa = await _get_etapa_by_nombre(session, etapa_nombre)

    if nueva_etapa.orden >= (await _get_etapa_by_nombre(session, ETAPA_PRIMERA_COMPRA)).orden:
        contacto = await session.get(CrmContacto, oportunidad.contacto_id)
        if contacto.erp_cliente_id is None or not await _has_erp_purchase(session, contacto.erp_cliente_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contacto must have a linked ERP purchase before reaching 'Primera Compra'",
            )

    etapa_anterior = oportunidad.etapa_nombre
    if etapa_anterior != nueva_etapa.nombre:
        await crm_auditoria_service.log_change(
            session, "Oportunidad", oportunidad_id, usuario_id, "etapa", etapa_anterior, nueva_etapa.nombre
        )
    oportunidad.etapa_id = nueva_etapa.id
    await session.commit()
    return await get_oportunidad(session, oportunidad_id)


async def add_actividad(
    session: AsyncSession, oportunidad_id: int, payload: CrmActividadCreate
) -> CrmActividad:
    await get_oportunidad(session, oportunidad_id)
    actividad = CrmActividad(oportunidad_id=oportunidad_id, **payload.model_dump())
    session.add(actividad)
    await session.commit()
    await session.refresh(actividad)
    return actividad


async def list_actividades(session: AsyncSession, oportunidad_id: int) -> list[CrmActividad]:
    await get_oportunidad(session, oportunidad_id)
    result = await session.execute(
        select(CrmActividad).where(CrmActividad.oportunidad_id == oportunidad_id).order_by(CrmActividad.fecha)
    )
    return list(result.scalars().all())
