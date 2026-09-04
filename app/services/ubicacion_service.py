from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ordenes_produccion import ProductoFabricado
from app.models.ubicacion import Ubicacion
from app.schemas.ubicacion import UbicacionCreate, UbicacionUpdate


async def list_ubicaciones(session: AsyncSession, q: str | None = None) -> list[Ubicacion]:
    stmt = select(Ubicacion).order_by(Ubicacion.nombre)
    if q:
        stmt = stmt.where(Ubicacion.nombre.ilike(f"%{q}%"))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_ubicacion(session: AsyncSession, ubicacion_id: int) -> Ubicacion:
    ubicacion = await session.get(Ubicacion, ubicacion_id)
    if ubicacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ubicacion not found")
    return ubicacion


async def create_ubicacion(session: AsyncSession, payload: UbicacionCreate) -> Ubicacion:
    ubicacion = Ubicacion(**payload.model_dump())
    session.add(ubicacion)
    await session.commit()
    await session.refresh(ubicacion)
    return ubicacion


async def update_ubicacion(session: AsyncSession, ubicacion: Ubicacion, payload: UbicacionUpdate) -> Ubicacion:
    for field, value in payload.model_dump().items():
        setattr(ubicacion, field, value)
    await session.commit()
    await session.refresh(ubicacion)
    return ubicacion


async def delete_ubicacion(session: AsyncSession, ubicacion: Ubicacion) -> None:
    stmt = select(ProductoFabricado.id).where(
        or_(ProductoFabricado.ubicacion_id == ubicacion.id, ProductoFabricado.ubicacion_desperdicio_id == ubicacion.id)
    ).limit(1)
    en_uso = (await session.execute(stmt)).scalar_one_or_none()
    if en_uso is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se puede eliminar: la ubicación está referenciada por un producto fabricado",
        )
    await session.delete(ubicacion)
    await session.commit()
