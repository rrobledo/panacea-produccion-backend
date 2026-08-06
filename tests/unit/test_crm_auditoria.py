from sqlalchemy import select

from app.models.crm_auditoria import CrmAuditoria
from app.models.user import User
from app.services import crm_auditoria_service


async def test_commercial_role_can_be_persisted(session):
    session.add(User(email="vendedor@example.com", role="vendedor"))
    await session.commit()

    result = await session.execute(select(User).where(User.email == "vendedor@example.com"))
    user = result.scalar_one()
    assert user.role == "vendedor"


async def test_log_create_persists_entry(session):
    await crm_auditoria_service.log_create(session, entidad="Contacto", entidad_id=1, usuario_id=None)
    await session.commit()

    result = await session.execute(select(CrmAuditoria).where(CrmAuditoria.entidad == "Contacto"))
    entry = result.scalar_one()
    assert entry.entidad_id == 1
    assert entry.campo is None


async def test_log_change_persists_entry_with_diff(session):
    user = User(email="admin@example.com", role="admin")
    session.add(user)
    await session.flush()

    await crm_auditoria_service.log_change(
        session,
        entidad="Contacto",
        entidad_id=1,
        usuario_id=user.id,
        campo="nombre",
        valor_anterior="Juan",
        valor_nuevo="Juan Perez",
    )
    await session.commit()

    result = await session.execute(select(CrmAuditoria).where(CrmAuditoria.campo == "nombre"))
    entry = result.scalar_one()
    assert entry.valor_anterior == "Juan"
    assert entry.valor_nuevo == "Juan Perez"
    assert entry.usuario_id == user.id
