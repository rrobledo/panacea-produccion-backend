from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.deps import get_session
from app.models.productos import Costos, Productos
from app.schemas.productos import CostoCreate, CostoRead, ProductoCreate, ProductoRead

router = APIRouter(prefix="/productos", tags=["productos"])


@router.get("", response_model=list[ProductoRead])
async def list_productos(
    nombre: str | None = None,
    q: str | None = None,
    solo_habilitados: bool = True,
    is_producto: bool | None = None,
    session: AsyncSession = Depends(get_session),
):
    busqueda = nombre or q
    if busqueda:
        stmt = select(Productos).where(Productos.nombre.ilike(f"%{busqueda}%")).order_by(Productos.nombre)
    else:
        stmt = select(Productos).order_by(Productos.prioridad, Productos.nombre)
    if solo_habilitados:
        stmt = stmt.where(Productos.habilitado.is_(True))
    if is_producto is not None:
        stmt = stmt.where(Productos.is_producto.is_(is_producto))
    result = await session.execute(stmt)
    return result.scalars().all()


async def _validate_producto_base(session: AsyncSession, producto_id: int | None, producto_base_id: int | None) -> None:
    if producto_base_id is None:
        return
    if producto_base_id == producto_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Un producto no puede ser su propio producto base"
        )
    base = await session.get(Productos, producto_base_id)
    if base is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="producto_base_id not found")
    if base.is_producto:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="producto_base_id debe apuntar a un producto intermedio (Producto Final = No)",
        )
    # Walk the chain of producto_base_id to detect a cycle back to producto_id.
    visited: set[int] = {producto_id} if producto_id is not None else set()
    current = base
    while current.producto_base_id is not None:
        if current.producto_base_id in visited:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="producto_base_id genera un ciclo de productos base",
            )
        visited.add(current.id)
        current = await session.get(Productos, current.producto_base_id)
        if current is None:
            break


@router.post("", response_model=ProductoRead, status_code=status.HTTP_201_CREATED)
async def create_producto(payload: ProductoCreate, session: AsyncSession = Depends(get_session)):
    await _validate_producto_base(session, None, payload.producto_base_id)
    producto = Productos(**payload.model_dump())
    session.add(producto)
    await session.commit()
    # session.get() (not refresh) re-triggers the lazy="joined" load for
    # producto_base — refresh(attribute_names=[...]) doesn't reliably eager
    # load self-referential relationships in an async session.
    return await _get_producto_or_404(session, producto.id)


async def _get_producto_or_404(session: AsyncSession, producto_id: int) -> Productos:
    stmt = (
        select(Productos)
        .options(joinedload(Productos.producto_base))
        .where(Productos.id == producto_id)
        .execution_options(populate_existing=True)
    )
    producto = (await session.execute(stmt)).unique().scalar_one_or_none()
    if producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto not found")
    return producto


@router.get("/{producto_id}", response_model=ProductoRead)
async def get_producto(producto_id: int, session: AsyncSession = Depends(get_session)):
    return await _get_producto_or_404(session, producto_id)


@router.put("/{producto_id}", response_model=ProductoRead)
async def update_producto(producto_id: int, payload: ProductoCreate, session: AsyncSession = Depends(get_session)):
    producto = await _get_producto_or_404(session, producto_id)
    await _validate_producto_base(session, producto_id, payload.producto_base_id)
    for field, value in payload.model_dump().items():
        setattr(producto, field, value)
    await session.commit()
    return await _get_producto_or_404(session, producto_id)


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
