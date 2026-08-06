from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CRM_ROLES, require_role
from app.deps import get_session
from app.models.user import User
from app.schemas.crm_club_socio import CrmClubSocioLinkRequest, CrmClubSocioRead
from app.services import crm_club_socio_service

router = APIRouter(prefix="/crm/contactos/{contacto_id}/club-socio", tags=["crm-integracion-club-socios"])


@router.get("", response_model=CrmClubSocioRead | None)
async def get_estado(
    contacto_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_club_socio_service.get_estado(session, contacto_id)


@router.put("", response_model=CrmClubSocioRead)
async def link_socio(
    contacto_id: int,
    payload: CrmClubSocioLinkRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_club_socio_service.link_socio(session, contacto_id, payload.socio_id)
