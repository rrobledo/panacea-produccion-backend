from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clientes import Clientes
from app.models.crm_contacto import CrmContacto
from app.services import crm_auditoria_service

_HISTORIAL_STMT = text(
    """
    SELECT document_id, operation_date, SUM(count) AS cantidad, SUM(subtotal) AS total
      FROM panacea_sales_v2
     WHERE customer_id = :cid
     GROUP BY document_id, operation_date
     ORDER BY operation_date DESC
    """
)

_TOP_PRODUCTOS_STMT = text(
    """
    SELECT product_id, product, SUM(count) AS cantidad, SUM(subtotal) AS total
      FROM panacea_sales_v2
     WHERE customer_id = :cid
     GROUP BY product_id, product
     ORDER BY cantidad DESC
     LIMIT :limit
    """
)


async def link_erp_cliente(session: AsyncSession, contacto_id: int, erp_cliente_id: int, usuario_id: int | None) -> CrmContacto:
    contacto = await session.get(CrmContacto, contacto_id)
    if contacto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto not found")
    if await session.get(Clientes, erp_cliente_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="erp_cliente_id does not reference an existing row")

    if contacto.erp_cliente_id != erp_cliente_id:
        await crm_auditoria_service.log_change(
            session, "Contacto", contacto_id, usuario_id, "erp_cliente_id", contacto.erp_cliente_id, erp_cliente_id
        )
    contacto.erp_cliente_id = erp_cliente_id
    await session.commit()
    await session.refresh(contacto)
    return contacto


async def get_historial_compras(session: AsyncSession, contacto_id: int) -> list[dict]:
    contacto = await session.get(CrmContacto, contacto_id)
    if contacto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto not found")
    if contacto.erp_cliente_id is None:
        return []
    result = await session.execute(_HISTORIAL_STMT, {"cid": contacto.erp_cliente_id})
    return [dict(row) for row in result.mappings().all()]


async def get_productos_mas_consumidos(session: AsyncSession, contacto_id: int, limite: int = 5) -> list[dict]:
    contacto = await session.get(CrmContacto, contacto_id)
    if contacto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto not found")
    if contacto.erp_cliente_id is None:
        return []
    result = await session.execute(_TOP_PRODUCTOS_STMT, {"cid": contacto.erp_cliente_id, "limit": limite})
    return [dict(row) for row in result.mappings().all()]


async def autovincular_por_email(session: AsyncSession) -> list[int]:
    """Reconciliation pass: links Contactos without erp_cliente_id to a
    `clientes` row with a matching email that has at least one ERP sale.
    Coarse heuristic (RN-003) — meant to run periodically, not as a
    real-time trigger, since `panacea_sales_v2` is externally populated
    with no change-event this app can hook into.
    """
    stmt = select(CrmContacto).where(CrmContacto.erp_cliente_id.is_(None), CrmContacto.email.is_not(None))
    contactos = (await session.execute(stmt)).scalars().all()

    vinculados: list[int] = []
    for contacto in contactos:
        cliente = (
            await session.execute(
                select(Clientes).where(Clientes.email1.is_not(None), Clientes.email1.ilike(contacto.email))
            )
        ).scalars().first()
        if cliente is None:
            continue
        has_purchase = (
            await session.execute(text("SELECT 1 FROM panacea_sales_v2 WHERE customer_id = :cid LIMIT 1"), {"cid": cliente.id})
        ).first()
        if has_purchase is None:
            continue
        await crm_auditoria_service.log_change(
            session, "Contacto", contacto.id, None, "erp_cliente_id", None, cliente.id
        )
        contacto.erp_cliente_id = cliente.id
        vinculados.append(contacto.id)

    await session.commit()
    return vinculados
