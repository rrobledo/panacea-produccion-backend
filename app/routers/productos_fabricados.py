from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.schemas.ordenes_produccion import ProductoFabricadoRead
from app.services import ordenes_produccion_service as service

router = APIRouter(prefix="/productos_fabricados", tags=["productos-fabricados"])


@router.get("", response_model=list[ProductoFabricadoRead])
async def list_productos_fabricados(
    producto_id: int | None = None,
    ubicacion_id: int | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    session: AsyncSession = Depends(get_session),
):
    rows = await service.list_productos_fabricados(
        session, producto_id=producto_id, ubicacion_id=ubicacion_id, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
    )
    return [ProductoFabricadoRead.from_orm_row(r) for r in rows]
