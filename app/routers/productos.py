from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.models.productos import Costos, Productos
from app.schemas.productos import CostoCreate, CostoRead, ProductoCreate, ProductoRead

router = APIRouter(prefix="/productos", tags=["productos"])


@router.get("", response_model=list[ProductoRead])
async def list_productos(
    nombre: str | None = None,
    q: str | None = None,
    solo_habilitados: bool = True,
    session: AsyncSession = Depends(get_session),
):
    busqueda = nombre or q
    if busqueda:
        stmt = select(Productos).where(Productos.nombre.ilike(f"%{busqueda}%")).order_by(Productos.nombre)
    else:
        stmt = select(Productos).order_by(Productos.prioridad, Productos.nombre)
    if solo_habilitados:
        stmt = stmt.where(Productos.habilitado.is_(True))
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ProductoRead, status_code=status.HTTP_201_CREATED)
async def create_producto(payload: ProductoCreate, session: AsyncSession = Depends(get_session)):
    producto = Productos(**payload.model_dump())
    session.add(producto)
    await session.commit()
    await session.refresh(producto)
    return producto


async def _get_producto_or_404(session: AsyncSession, producto_id: int) -> Productos:
    producto = await session.get(Productos, producto_id)
    if producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto not found")
    return producto


@router.get("/{producto_id}", response_model=ProductoRead)
async def get_producto(producto_id: int, session: AsyncSession = Depends(get_session)):
    return await _get_producto_or_404(session, producto_id)


@router.put("/{producto_id}", response_model=ProductoRead)
async def update_producto(producto_id: int, payload: ProductoCreate, session: AsyncSession = Depends(get_session)):
    producto = await _get_producto_or_404(session, producto_id)
    for field, value in payload.model_dump().items():
        setattr(producto, field, value)
    await session.commit()
    await session.refresh(producto)
    return producto


@router.delete("/{producto_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_producto(producto_id: int, session: AsyncSession = Depends(get_session)):
    producto = await _get_producto_or_404(session, producto_id)
    await session.delete(producto)
    await session.commit()


@router.get("/{producto_id}/costos", response_model=list[CostoRead])
async def list_costos(producto_id: int, session: AsyncSession = Depends(get_session)):
    stmt = select(Costos).where(Costos.producto_id == producto_id)
    result = await session.execute(stmt)
    return [CostoRead.from_orm_row(row) for row in result.scalars().all()]


@router.post(
    "/{producto_id}/costos",
    response_model=CostoRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_costo(producto_id: int, payload: CostoCreate, session: AsyncSession = Depends(get_session)):
    await _get_producto_or_404(session, producto_id)
    costo = Costos(producto_id=producto_id, insumo_id=payload.insumo, cantidad=payload.cantidad)
    session.add(costo)
    await session.commit()
    await session.refresh(costo, attribute_names=["insumo"])
    return CostoRead.from_orm_row(costo)


async def _get_costo_or_404(session: AsyncSession, producto_id: int, costo_id: int) -> Costos:
    stmt = select(Costos).where(Costos.id == costo_id, Costos.producto_id == producto_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Costo not found")
    return row


@router.put("/{producto_id}/costos/{costo_id}", response_model=CostoRead)
async def update_costo(
    producto_id: int, costo_id: int, payload: CostoCreate, session: AsyncSession = Depends(get_session)
):
    costo = await _get_costo_or_404(session, producto_id, costo_id)
    costo.insumo_id = payload.insumo
    costo.cantidad = payload.cantidad
    await session.commit()
    await session.refresh(costo, attribute_names=["insumo"])
    return CostoRead.from_orm_row(costo)


@router.delete(
    "/{producto_id}/costos/{costo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_costo(producto_id: int, costo_id: int, session: AsyncSession = Depends(get_session)):
    costo = await _get_costo_or_404(session, producto_id, costo_id)
    await session.delete(costo)
    await session.commit()
