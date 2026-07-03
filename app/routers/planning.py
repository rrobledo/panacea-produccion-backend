from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_api_key
from app.services import planning_service

router = APIRouter(tags=["planning"])


@router.get("/planning")
async def list_planning(anio: int = 2025, session: AsyncSession = Depends(get_session)):
    return await planning_service.get_planning(session, anio)


@router.post("/planning", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
async def bulk_update_planning(payload: list[dict], session: AsyncSession = Depends(get_session)):
    await planning_service.update_planificacion(session, payload)


@router.get("/planning_columnas")
async def list_planning_columnas(anio: int = 2024, session: AsyncSession = Depends(get_session)):
    return await planning_service.get_planning_columnas(session, anio)


@router.post("/planning/generate", dependencies=[Depends(require_api_key)])
async def generate_planning(
    year: int = datetime.now().year,
    producto_id: int | None = None,
    dry_run: bool = True,
    session: AsyncSession = Depends(get_session),
):
    return await planning_service.generate_planning(session, year, producto_id, dry_run)
