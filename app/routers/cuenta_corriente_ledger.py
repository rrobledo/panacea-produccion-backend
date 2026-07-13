from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.services import movimiento_cc_service as service

# Split from the (legacy, retiring) app/routers/cuenta_corriente.py so that
# file can be deleted wholesale once /ctacteprov* is retired (Group 10)
# without touching these new endpoints.
proveedor_ledger_router = APIRouter(prefix="/proveedores", tags=["cuenta-corriente"])
resumen_router = APIRouter(prefix="/cuenta-corriente", tags=["cuenta-corriente"])


@proveedor_ledger_router.get("/{proveedor_id}/cuenta-corriente")
async def get_cuenta_corriente_ledger(
    proveedor_id: int,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await service.get_ledger(session, proveedor_id, fecha_desde, fecha_hasta)


@resumen_router.get("/resumen")
async def get_cuenta_corriente_resumen(
    fecha_desde: date,
    fecha_hasta: date,
    session: AsyncSession = Depends(get_session),
):
    return await service.get_resumen(session, fecha_desde, fecha_hasta)


@resumen_router.get("/saldos")
async def get_cuenta_corriente_saldos(session: AsyncSession = Depends(get_session)):
    return await service.get_saldos_por_proveedor(session)
