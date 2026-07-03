from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, require_api_key
from app.services import programacion_service

router = APIRouter(tags=["programacion"])


@router.get("/programacion")
async def list_programacion(
    anio: int = 2025,
    mes: int = 9,
    responsable: str | None = None,
    semana: int = 0,
    session: AsyncSession = Depends(get_session),
):
    return await programacion_service.get_programacion(session, anio, mes, responsable, semana)


@router.post("/programacion", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
async def bulk_update_programacion(payload: list[dict], session: AsyncSession = Depends(get_session)):
    await programacion_service.update_programacion(session, payload)


@router.get("/programacion_columnas")
async def list_programacion_columnas(
    anio: int = 2025, mes: int = 9, semana: int = 0, session: AsyncSession = Depends(get_session)
):
    return await programacion_service.get_programacion_columnas(session, anio, mes, semana)


@router.post("/programacion/generate", dependencies=[Depends(require_api_key)])
async def generate_programacion(
    year: int = datetime.now().year,
    month: int = datetime.now().month,
    prev_year: int | None = None,
    prev_month: int | None = None,
    producto_id: int | None = None,
    dry_run: bool = True,
    session: AsyncSession = Depends(get_session),
):
    return await programacion_service.generate_programacion(
        session, year, month, prev_year, prev_month, producto_id, dry_run
    )


@router.post("/programacion/copy-week", dependencies=[Depends(require_api_key)])
async def copy_week(
    from_year: int,
    from_week: int,
    to_year: int,
    to_week: int,
    dry_run: bool = True,
    session: AsyncSession = Depends(get_session),
):
    return await programacion_service.copy_week(session, from_year, from_week, to_year, to_week, dry_run)
