from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.schemas.procesos import ProcesoRead, ProcesoWrite
from app.services import maquinaria_service
from app.services import procesos_service as service

router = APIRouter(prefix="/procesos", tags=["procesos"])


async def _leer(session: AsyncSession, proceso) -> ProcesoRead:
    """Arma la respuesta con sus operaciones y sus advertencias.

    Entre las advertencias entra la del lote contra la capacidad de la
    amasadora: avisa cuánto se desperdicia de la última bacha, sin bloquear
    (design.md D13).
    """
    advertencias = await service.advertencias_de(proceso)
    aviso_lote = await maquinaria_service.advertencia_de_lote(session, proceso)
    if aviso_lote:
        advertencias = advertencias + [aviso_lote]
    operaciones = await maquinaria_service.operaciones_de_proceso(session, proceso.id)
    return ProcesoRead.from_orm_row(proceso, advertencias, operaciones)


@router.get("", response_model=list[ProcesoRead])
async def list_procesos(
    tipo: str | None = None,
    incluir_historicas: bool = False,
    session: AsyncSession = Depends(get_session),
):
    procesos = await service.list_procesos(session, tipo, incluir_historicas)
    return [ProcesoRead.from_orm_row(proceso) for proceso in procesos]


@router.post("", response_model=ProcesoRead, status_code=status.HTTP_201_CREATED)
async def create_proceso(payload: ProcesoWrite, session: AsyncSession = Depends(get_session)):
    proceso = await service.crear_proceso(session, payload)
    return await _leer(session, proceso)


# Antes de `/{proceso_id}`: si no, FastAPI intenta leer "pendientes-relevamiento"
# como un entero y responde 422.
@router.get("/pendientes-relevamiento")
async def pendientes_relevamiento(session: AsyncSession = Depends(get_session)):
    return await service.pendientes_de_relevamiento(session)


@router.get("/{proceso_id}", response_model=ProcesoRead)
async def get_proceso(proceso_id: int, session: AsyncSession = Depends(get_session)):
    # Devuelve el grafo completo del proceso, que es lo que el frontend no
    # podía obtener hasta ahora: no había endpoint que expusiera la receta, así
    # que el preview mostraba el resultado de la explosión sin poder
    # reproducirla (preview-generacion-ordenes/design.md:7).
    proceso = await service.get_proceso(session, proceso_id)
    return await _leer(session, proceso)


@router.put("/{proceso_id}", response_model=ProcesoRead)
async def update_proceso(proceso_id: int, payload: ProcesoWrite, session: AsyncSession = Depends(get_session)):
    proceso = await service.get_proceso(session, proceso_id)
    actualizado = await service.actualizar_proceso(session, proceso, payload)
    return await _leer(session, actualizado)


@router.delete("/{proceso_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proceso(proceso_id: int, session: AsyncSession = Depends(get_session)):
    proceso = await service.get_proceso(session, proceso_id)
    await service.eliminar_proceso(session, proceso)
