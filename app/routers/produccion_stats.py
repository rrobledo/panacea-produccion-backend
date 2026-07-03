from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.services import analytics_service

router = APIRouter(tags=["produccion-analytics"])


@router.get("/get_produccion_by_category")
async def produccion_by_category(
    anio: int = datetime.now().year, mes: int = datetime.now().month, session: AsyncSession = Depends(get_session)
):
    return await analytics_service.get_produccion_by_category(session, anio, mes)


@router.get("/get_produccion_by_productos")
async def produccion_by_productos(
    anio: int = datetime.now().year, mes: int = datetime.now().month, session: AsyncSession = Depends(get_session)
):
    return await analytics_service.get_produccion_by_productos(session, anio, mes)


@router.get("/get_insumos_by_month")
async def insumos_by_month(
    anio: int = datetime.now().year,
    mes: int = datetime.now().month,
    semana: int = 0,
    by_week: str = "yes",
    session: AsyncSession = Depends(get_session),
):
    return await analytics_service.get_insumos_by_month(session, anio, mes, semana, by_week == "yes")
