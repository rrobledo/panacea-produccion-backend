from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_contacto import CrmContacto
from app.models.crm_segmento import CrmContactoSegmento, CrmSegmento
from app.schemas.crm_segmento import CrmSegmentoCreate


async def list_segmentos(session: AsyncSession) -> list[CrmSegmento]:
    result = await session.execute(select(CrmSegmento).order_by(CrmSegmento.nombre))
    return list(result.scalars().all())


async def get_segmento(session: AsyncSession, segmento_id: int) -> CrmSegmento:
    segmento = await session.get(CrmSegmento, segmento_id)
    if segmento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segmento not found")
    return segmento


async def create_segmento(session: AsyncSession, payload: CrmSegmentoCreate) -> CrmSegmento:
    segmento = CrmSegmento(nombre=payload.nombre, criterio=payload.criterio.model_dump(exclude_none=True))
    session.add(segmento)
    await session.commit()
    await session.refresh(segmento)
    return segmento


def _matching_contactos_stmt(criterio: dict):
    stmt = select(CrmContacto.id)
    for field in ("tipo", "empresa_id", "rubro_id", "ciudad_id", "origen_id"):
        value = criterio.get(field)
        if value is not None:
            stmt = stmt.where(getattr(CrmContacto, field) == value)
    return stmt


async def recompute_all(session: AsyncSession) -> dict[int, int]:
    """Recomputes membership for every Segmento. Returns {segmento_id: contactos count}."""
    segmentos = await list_segmentos(session)
    counts: dict[int, int] = {}
    for segmento in segmentos:
        contacto_ids = (await session.execute(_matching_contactos_stmt(segmento.criterio))).scalars().all()
        await session.execute(delete(CrmContactoSegmento).where(CrmContactoSegmento.segmento_id == segmento.id))
        session.add_all(
            [CrmContactoSegmento(segmento_id=segmento.id, contacto_id=cid) for cid in contacto_ids]
        )
        counts[segmento.id] = len(contacto_ids)
    await session.commit()
    return counts


async def list_miembros(session: AsyncSession, segmento_id: int) -> list[CrmContactoSegmento]:
    await get_segmento(session, segmento_id)
    result = await session.execute(
        select(CrmContactoSegmento).where(CrmContactoSegmento.segmento_id == segmento_id)
    )
    return list(result.scalars().all())
