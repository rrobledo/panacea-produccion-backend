from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.clientes import Clientes
from app.models.crm_catalogos import CrmCiudad, CrmOrigen, CrmRubro
from app.models.crm_contacto import CrmContacto
from app.models.crm_empresa import CrmEmpresa
from app.schemas.crm_contacto import CrmContactoBase, CrmContactoCreate, CrmContactoUpdate
from app.services import crm_auditoria_service

_RELATION_OPTIONS = (
    selectinload(CrmContacto.empresa),
    selectinload(CrmContacto.rubro),
    selectinload(CrmContacto.ciudad),
    selectinload(CrmContacto.origen),
)


async def _validate_references(session: AsyncSession, payload: CrmContactoBase) -> None:
    checks = [
        (payload.empresa_id, CrmEmpresa, "empresa_id"),
        (payload.rubro_id, CrmRubro, "rubro_id"),
        (payload.ciudad_id, CrmCiudad, "ciudad_id"),
        (payload.origen_id, CrmOrigen, "origen_id"),
        (payload.erp_cliente_id, Clientes, "erp_cliente_id"),
    ]
    for value, model, field in checks:
        if value is not None and await session.get(model, value) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field} does not reference an existing row")


async def get_contacto(session: AsyncSession, contacto_id: int) -> CrmContacto:
    stmt = (
        select(CrmContacto)
        .options(*_RELATION_OPTIONS)
        .where(CrmContacto.id == contacto_id)
        # Same rationale as compra_service.get_compra: without this, a
        # contacto already in the identity map (e.g. just added in this
        # session) is returned as-is, with empresa/rubro/ciudad/origen
        # still unloaded despite the selectinload options above.
        .execution_options(populate_existing=True)
    )
    contacto = (await session.execute(stmt)).scalar_one_or_none()
    if contacto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto not found")
    return contacto


async def list_contactos(
    session: AsyncSession,
    empresa_id: int | None = None,
    tipo: str | None = None,
    q: str | None = None,
) -> list[CrmContacto]:
    stmt = select(CrmContacto).options(*_RELATION_OPTIONS).order_by(CrmContacto.nombre)
    if empresa_id is not None:
        stmt = stmt.where(CrmContacto.empresa_id == empresa_id)
    if tipo is not None:
        stmt = stmt.where(CrmContacto.tipo == tipo)
    if q:
        stmt = stmt.where(CrmContacto.nombre.ilike(f"%{q}%"))
    stmt = stmt.execution_options(populate_existing=True)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_contacto(session: AsyncSession, payload: CrmContactoCreate, usuario_id: int | None) -> CrmContacto:
    await _validate_references(session, payload)
    contacto = CrmContacto(**payload.model_dump())
    session.add(contacto)
    await session.flush()
    await crm_auditoria_service.log_create(session, "Contacto", contacto.id, usuario_id)
    await session.commit()
    return await get_contacto(session, contacto.id)


async def update_contacto(
    session: AsyncSession, contacto_id: int, payload: CrmContactoUpdate, usuario_id: int | None
) -> CrmContacto:
    contacto = await get_contacto(session, contacto_id)
    await _validate_references(session, payload)
    for field, value in payload.model_dump().items():
        previous = getattr(contacto, field)
        if previous != value:
            await crm_auditoria_service.log_change(session, "Contacto", contacto_id, usuario_id, field, previous, value)
        setattr(contacto, field, value)
    await session.commit()
    return await get_contacto(session, contacto_id)
