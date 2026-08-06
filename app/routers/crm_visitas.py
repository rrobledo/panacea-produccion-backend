from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CRM_ROLES, require_role
from app.deps import get_session
from app.models.user import User
from app.schemas.crm_visita import CrmVisitaCreate, CrmVisitaRead
from app.services import crm_visita_service

router = APIRouter(prefix="/crm/visitas", tags=["crm-visitas"])


@router.get("", response_model=list[CrmVisitaRead])
async def list_visitas(
    contacto_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_visita_service.list_visitas(session, contacto_id=contacto_id)


@router.post("", response_model=CrmVisitaRead, status_code=201)
async def create_visita(
    payload: CrmVisitaCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_visita_service.create_visita(session, payload, usuario_id=current_user.id)


@router.get("/{visita_id}", response_model=CrmVisitaRead)
async def get_visita(
    visita_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_visita_service.get_visita(session, visita_id)
