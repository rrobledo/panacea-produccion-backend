from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_club_socio import CrmClubSocioCache
from app.models.crm_contacto import CrmContacto
from app.services.club_socios_client import ClubSociosClient, get_club_socios_client


async def get_estado(session: AsyncSession, contacto_id: int) -> CrmClubSocioCache | None:
    if await session.get(CrmContacto, contacto_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto not found")
    result = await session.execute(select(CrmClubSocioCache).where(CrmClubSocioCache.contacto_id == contacto_id))
    return result.scalar_one_or_none()


async def link_socio(session: AsyncSession, contacto_id: int, socio_id: str) -> CrmClubSocioCache:
    if await session.get(CrmContacto, contacto_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto not found")

    existing = await get_estado(session, contacto_id)
    if existing is not None:
        existing.socio_id = socio_id
        cache_row = existing
    else:
        cache_row = CrmClubSocioCache(contacto_id=contacto_id, socio_id=socio_id)
        session.add(cache_row)

    await session.commit()
    await session.refresh(cache_row)
    return cache_row


async def refresh_all(session: AsyncSession, client: ClubSociosClient | None = None) -> int:
    client = client or get_club_socios_client()
    result = await session.execute(select(CrmClubSocioCache))
    rows = list(result.scalars().all())

    refreshed = 0
    for row in rows:
        # Errors from the external client degrade gracefully: the row
        # simply keeps its last-known cached values (design.md — a dashboard
        # read must never depend on the Club de Socios API being up).
        try:
            info = await client.fetch_socio(row.socio_id)
        except Exception:
            continue
        if info is None:
            continue
        row.categoria = info.categoria
        row.puntos = info.puntos
        row.fecha_alta = info.fecha_alta
        refreshed += 1

    await session.commit()
    return refreshed
