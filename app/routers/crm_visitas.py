from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_authenticated
from app.deps import get_session
from app.models.user import User
from app.schemas.crm_visita import CrmVisitaAdjuntoRead, CrmVisitaCreate, CrmVisitaRead
from app.services import crm_visita_service

router = APIRouter(prefix="/crm/visitas", tags=["crm-visitas"])


@router.get("", response_model=list[CrmVisitaRead])
async def list_visitas(
    contacto_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_visita_service.list_visitas(session, contacto_id=contacto_id)


@router.post("", response_model=CrmVisitaRead, status_code=201)
async def create_visita(
    payload: CrmVisitaCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_visita_service.create_visita(session, payload, usuario_id=current_user.id)


@router.get("/{visita_id}", response_model=CrmVisitaRead)
async def get_visita(
    visita_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_visita_service.get_visita(session, visita_id)


@router.post("/{visita_id}/adjuntos", response_model=CrmVisitaAdjuntoRead, status_code=201)
async def upload_adjunto(
    visita_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    content = await file.read()
    return await crm_visita_service.add_adjunto(session, visita_id, file.filename, content, file.content_type)


@router.get("/{visita_id}/adjuntos", response_model=list[CrmVisitaAdjuntoRead])
async def list_adjuntos(
    visita_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    return await crm_visita_service.list_adjuntos(session, visita_id)


@router.get("/{visita_id}/adjuntos/{adjunto_id}")
async def download_adjunto(
    visita_id: int,
    adjunto_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_authenticated()),
):
    adjunto = await crm_visita_service.get_adjunto(session, visita_id, adjunto_id)
    return Response(
        content=adjunto.contenido,
        media_type=adjunto.tipo or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{adjunto.nombre}"'},
    )
