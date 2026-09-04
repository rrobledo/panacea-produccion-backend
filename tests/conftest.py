import os
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.utils import create_token
from app.config import get_settings
from app.deps import get_session, require_api_key
from app.main import app
from app.models.user import User

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://panacea:panacea@localhost:55432/panacea_test"
)

TRUNCATE_TABLES = [
    "users",
    "productos_fabricados",
    "ordenes_produccion_insumo_linea",
    "ordenes_produccion_producto_linea",
    "ordenes_produccion",
    "stock_movimientos",
    "ubicaciones_ubicacion",
    "crm_auditoria",
    "crm_club_socio_cache",
    "crm_actividad",
    "crm_oportunidad",
    "crm_visita",
    "crm_contacto_segmento",
    "crm_segmento",
    "crm_contacto_campana",
    "crm_campana",
    "crm_contacto",
    "crm_empresa",
    "crm_vendedor",
    "crm_rubro",
    "crm_ciudad",
    "crm_origen",
    "compras_movimiento_cc",
    "compras_pago_aplicacion",
    "compras_pago_medio",
    "compras_pago",
    "compras_compra_adjunto",
    "compras_compra_impuesto",
    "compras_compra_detalle",
    "compras_orden_compra_detalle",
    "compras_compra",
    "compras_orden_compra",
    "compras_item_gasto",
    "costos_cuentacorrienteproveedorafect",
    "costos_cuentacorrienteproveedordetalle",
    "costos_cuentacorrienteproveedor",
    "costos_proveedor",
    "remitos_remito_detalle",
    "remitos_remito",
    "pedidos_pedido_detalle",
    "pedidos_pedido",
    "sucursales_sucursal",
    "costos_remitodetalles",
    "costos_remitos",
    "clientes",
    "costos_costos",
    "costos_productosref",
    "costos_planificacion",
    "costos_programacion",
    "planificacion2024",
    "panacea_sales_v2",
    "costos_productos",
    "costos_insumos",
    "articulos_final",
]


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL)
    # Truncate before (not just after) each test: a hard-killed previous run
    # (e.g. an interrupted/hung test) skips teardown entirely, and this
    # container's data persists across pytest invocations — truncating at
    # setup makes each test's starting state correct regardless of how the
    # last run ended.
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(session):
    async def _get_session_override():
        yield session

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[require_api_key] = lambda: None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_header(session, monkeypatch):
    """Async factory: `await auth_header("vendedor")` -> Authorization header dict.

    Creates a `users` row with the given role and mints a real JWT for it
    (bypassing /auth/register, which always forces role="user") so tests can
    exercise `require_role`-gated CRM endpoints for any commercial role.
    """
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    get_settings.cache_clear()

    async def _make(role: str, email: str | None = None) -> dict:
        user = User(email=email or f"{role}-{uuid.uuid4().hex[:8]}@example.com", role=role)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_token(user.id, user.email, user.role)
        return {"Authorization": f"Bearer {token}"}

    yield _make
    get_settings.cache_clear()
