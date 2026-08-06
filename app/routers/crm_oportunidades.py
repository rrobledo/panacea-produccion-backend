from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CRM_ROLES, require_role
from app.deps import get_session
from app.models.user import User
from app.schemas.crm_oportunidad import (
    CrmActividadCreate,
    CrmActividadRead,
    CrmOportunidadCreate,
    CrmOportunidadEtapaUpdate,
    CrmOportunidadRead,
)
from app.services import crm_oportunidad_service

router = APIRouter(prefix="/crm/oportunidades", tags=["crm-oportunidades"])


@router.get("", response_model=list[CrmOportunidadRead])
async def list_oportunidades(
    contacto_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_oportunidad_service.list_oportunidades(session, contacto_id=contacto_id)


@router.post("", response_model=CrmOportunidadRead, status_code=201)
async def create_oportunidad(
    payload: CrmOportunidadCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_oportunidad_service.create_oportunidad(session, payload, usuario_id=current_user.id)


@router.get("/{oportunidad_id}", response_model=CrmOportunidadRead)
async def get_oportunidad(
    oportunidad_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_oportunidad_service.get_oportunidad(session, oportunidad_id)


@router.put("/{oportunidad_id}/etapa", response_model=CrmOportunidadRead)
async def update_etapa(
    oportunidad_id: int,
    payload: CrmOportunidadEtapaUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_oportunidad_service.update_etapa(
        session, oportunidad_id, payload.etapa_nombre, usuario_id=current_user.id
    )


@router.post("/{oportunidad_id}/actividades", response_model=CrmActividadRead, status_code=201)
async def add_actividad(
    oportunidad_id: int,
    payload: CrmActividadCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_oportunidad_service.add_actividad(session, oportunidad_id, payload)


@router.get("/{oportunidad_id}/actividades", response_model=list[CrmActividadRead])
async def list_actividades(
    oportunidad_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role(*CRM_ROLES)),
):
    return await crm_oportunidad_service.list_actividades(session, oportunidad_id)
