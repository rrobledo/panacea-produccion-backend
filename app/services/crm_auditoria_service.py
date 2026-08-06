from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm_auditoria import CrmAuditoria


async def log_create(session: AsyncSession, entidad: str, entidad_id: int, usuario_id: int | None) -> None:
    session.add(CrmAuditoria(entidad=entidad, entidad_id=entidad_id, usuario_id=usuario_id))


async def log_change(
    session: AsyncSession,
    entidad: str,
    entidad_id: int,
    usuario_id: int | None,
    campo: str,
    valor_anterior: object,
    valor_nuevo: object,
) -> None:
    session.add(
        CrmAuditoria(
            entidad=entidad,
            entidad_id=entidad_id,
            campo=campo,
            valor_anterior=None if valor_anterior is None else str(valor_anterior),
            valor_nuevo=None if valor_nuevo is None else str(valor_nuevo),
            usuario_id=usuario_id,
        )
    )
