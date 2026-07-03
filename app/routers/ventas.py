from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.services import analytics_service

router = APIRouter(tags=["ventas"])


@router.get("/get_ventas_por_cliente")
async def ventas_por_cliente(
    anio: int = datetime.now().year,
    mes: int = datetime.now().month,
    cliente: str = "Todos",
    session: AsyncSession = Depends(get_session),
):
    return await analytics_service.get_ventas_por_cliente(session, anio, mes, cliente)
