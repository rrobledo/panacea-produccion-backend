from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.services import costeo_service

router = APIRouter(tags=["costeo"])


@router.get("/costos_materia_prima")
async def list_costos_materia_prima(
    cantidad_lotes: int | None = None,
    lote_produccion: int | None = None,
    utilidad: float | None = None,
    precio_actual: float | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await costeo_service.get_all_cost(session, cantidad_lotes, lote_produccion, utilidad, precio_actual)


@router.get("/costos_materia_prima/{producto_id}")
async def get_costos_materia_prima(
    producto_id: int,
    cantidad_lotes: int | None = None,
    lote_produccion: int | None = None,
    utilidad: float | None = None,
    precio_actual: float | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await costeo_service.get_cost_by_product(
        session, producto_id, cantidad_lotes, lote_produccion, utilidad, precio_actual
    )


@router.get("/precio_productos")
async def get_precio_productos(mes: int | None = None, session: AsyncSession = Depends(get_session)):
    return await costeo_service.get_precio_productos(session, mes)
