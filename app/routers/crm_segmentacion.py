from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CRM_ROLES, require_role
from app.deps import get_session
from app.models.user import User
from app.schemas.crm_segmento import CrmContactoSegmentoRead, CrmSegmentoCreate, CrmSegmentoRead
from app.services import crm_segmentacion_service

router = APIRouter(prefix="/crm/segmentos", tags=["crm-segmentacion"])


@router.get("", response_model=list[CrmSegmentoRead])
async def list_segmentos(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(require_role(*CRM_ROLES))
):
    return await crm_segmentacion_service.list_segmentos(session)


@router.post("", response_model=CrmSegmentoRead, status_code=201)
async def create_segmento(
    payload: CrmSegmentoCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_segmentacion_service.create_segmento(session, payload)


@router.get("/{segmento_id}", response_model=CrmSegmentoRead)
async def get_segmento(
    segmento_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_segmentacion_service.get_segmento(session, segmento_id)


@router.get("/{segmento_id}/miembros", response_model=list[CrmContactoSegmentoRead])
async def list_miembros(
    segmento_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_segmentacion_service.list_miembros(session, segmento_id)


@router.post("/recompute")
async def recompute_segmentos(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    counts = await crm_segmentacion_service.recompute_all(session)
    return {"segmentos_recalculados": len(counts), "counts": counts}
