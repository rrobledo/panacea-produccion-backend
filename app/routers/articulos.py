from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.models.productos import Productos
from app.schemas.articulos import MovimientoArticuloRead, StockArticuloRead
from app.services import stock_service

router = APIRouter(prefix="/articulos", tags=["articulos"])


@router.get("", response_model=list[StockArticuloRead])
async def list_stock_articulos(
    naturaleza: str = "SEMIELABORADO", session: AsyncSession = Depends(get_session)
):
    # Sin movimientos en el listado: el historial se pide por artículo. Traerlo
    # para todos convertiría una pantalla de saldos en una descarga del ledger.
    productos = list(
        (
            await session.execute(
                select(Productos)
                .where(Productos.naturaleza == naturaleza, Productos.habilitado.is_(True))
                .order_by(Productos.nombre)
            )
        ).scalars().all()
    )
    disponibles = await stock_service.disponible_de_articulos(session, [p.id for p in productos])
    return [
        StockArticuloRead(
            producto_id=producto.id,
            producto_nombre=producto.nombre,
            naturaleza=producto.naturaleza,
            unidad_base=producto.unidad_base,
            disponible=disponibles.get(producto.id, 0.0),
            comprometido=await stock_service.comprometido_de_articulo(session, producto.id),
        )
        for producto in productos
    ]


@router.get("/{producto_id}/movimientos", response_model=StockArticuloRead)
async def get_stock_articulo(producto_id: int, session: AsyncSession = Depends(get_session)):
    producto = (
        await session.execute(select(Productos).where(Productos.id == producto_id))
    ).scalars().first()
    if producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artículo no encontrado")

    movimientos = await stock_service.list_movimientos_articulo(session, producto_id)
    return StockArticuloRead(
        producto_id=producto.id,
        producto_nombre=producto.nombre,
        naturaleza=producto.naturaleza,
        unidad_base=producto.unidad_base,
        disponible=await stock_service.disponible_de_articulo(session, producto_id),
        comprometido=await stock_service.comprometido_de_articulo(session, producto_id),
        movimientos=[MovimientoArticuloRead.model_validate(m) for m in movimientos],
    )
