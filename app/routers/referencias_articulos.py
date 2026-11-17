from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.schemas.referencias_articulos import (
    ArticuloReferenciaRead,
    ReferenciasArticuloWrite,
    ReferenciasArticulosRead,
    Sucursal,
)
from app.services import referencias_articulos_service as service

router = APIRouter(prefix="/referencias-articulos", tags=["referencias-articulos"])


@router.get("", response_model=ReferenciasArticulosRead)
async def list_referencias_articulos(
    estado: Literal["pendiente", "vinculado", "todos"] = "pendiente",
    sucursal: Sucursal | None = None,
    categoria: str | None = None,
    q: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await service.listar_articulos(session, estado=estado, sucursal=sucursal, categoria=categoria, q=q)


@router.put("/{idarticulo}", response_model=ArticuloReferenciaRead)
async def put_referencias_articulo(
    idarticulo: int,
    payload: ReferenciasArticuloWrite,
    session: AsyncSession = Depends(get_session),
):
    return await service.reemplazar_relaciones(session, idarticulo, payload.relaciones)
