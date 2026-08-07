from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_authenticated
from app.deps import get_session
from app.models.user import User
from app.schemas.crm_campana import (
    CrmCampanaConversion,
    CrmCampanaCreate,
    CrmCampanaRead,
    CrmCampanaUpdate,
    CrmContactoCampanaCreate,
    CrmContactoCampanaRead,
)
from app.services import crm_campana_service

router = APIRouter(prefix="/crm/campanas", tags=["crm-campanas"])


@router.get("", response_model=list[CrmCampanaRead])
async def list_campanas(
    session: AsyncSession = Depends(get_session), current_user: User = Depends(require_authenticated())
):
    return await crm_campana_service.list_campanas(session)


@router.post("", response_model=CrmCampanaRead, status_code=201)
async def create_campana(
    payload: CrmCampanaCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_campana_service.create_campana(session, payload)


@router.get("/{campana_id}", response_model=CrmCampanaRead)
async def get_campana(
    campana_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_campana_service.get_campana(session, campana_id)


@router.put("/{campana_id}", response_model=CrmCampanaRead)
async def update_campana(
    campana_id: int,
    payload: CrmCampanaUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_campana_service.update_campana(session, campana_id, payload)


@router.post("/{campana_id}/contactos", response_model=CrmContactoCampanaRead, status_code=201)
async def associate_contacto(
    campana_id: int,
    payload: CrmContactoCampanaCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_campana_service.associate_contacto(session, campana_id, payload.contacto_id)


@router.get("/{campana_id}/conversion", response_model=CrmCampanaConversion)
async def get_conversion(
    campana_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_campana_service.get_conversion(session, campana_id)
