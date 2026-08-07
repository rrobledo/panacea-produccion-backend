from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.models.crm_contacto import CrmContacto
from app.models.crm_vendedor import CrmVendedor
from app.models.crm_visita import CrmVisita, CrmVisitaAdjunto
from app.schemas.crm_visita import CrmVisitaCreate
from app.services import crm_auditoria_service

# Tipos aceptados para adjuntos de Visita — audio/video/imagen "para luego ser
# analizadas", no documentos genéricos.
ADJUNTO_TIPOS_PERMITIDOS = ("audio/", "video/", "image/")

# Vercel's default serverless request body limit is 4.5MB — este límite se
# aplica antes para dar un error claro en vez de que el platform lo corte
# con un 413 opaco. Si en el futuro hacen falta archivos más grandes (video
# largo), esto necesita una arquitectura distinta (upload directo a un
# object storage con URL prefirmada), no sólo subir este número.
ADJUNTO_MAX_BYTES = 4 * 1024 * 1024


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


async def add_adjunto(
    session: AsyncSession,
    visita_id: int,
    filename: str,
    content: bytes,
    content_type: str | None,
) -> CrmVisitaAdjunto:
    await get_visita(session, visita_id)  # 404 if missing

    if not content_type or not content_type.startswith(ADJUNTO_TIPOS_PERMITIDOS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sólo se aceptan archivos de audio, video o imagen",
        )
    if len(content) > ADJUNTO_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo supera el máximo permitido ({ADJUNTO_MAX_BYTES // (1024 * 1024)}MB)",
        )

    row = CrmVisitaAdjunto(visita_id=visita_id, nombre=filename, contenido=content, tipo=content_type)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_adjuntos(session: AsyncSession, visita_id: int) -> list[CrmVisitaAdjunto]:
    await get_visita(session, visita_id)  # 404 if missing
    stmt = (
        select(CrmVisitaAdjunto)
        .where(CrmVisitaAdjunto.visita_id == visita_id)
        .order_by(CrmVisitaAdjunto.fecha.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_adjunto(session: AsyncSession, visita_id: int, adjunto_id: int) -> CrmVisitaAdjunto:
    stmt = (
        select(CrmVisitaAdjunto)
        .options(undefer(CrmVisitaAdjunto.contenido))
        .where(CrmVisitaAdjunto.id == adjunto_id, CrmVisitaAdjunto.visita_id == visita_id)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Adjunto not found")
    return row
