from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.services import libro_iva_service as service

router = APIRouter(prefix="/libro-iva-compras", tags=["libro-iva-compras"])


@router.get("")
async def get_libro_iva_compras(periodo: str, session: AsyncSession = Depends(get_session)):
    return await service.get_libro_iva_compras(session, periodo)
