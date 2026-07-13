import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.deps import get_session, require_api_key
from app.main import app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://panacea:panacea@localhost:55432/panacea_test"
)

TRUNCATE_TABLES = [
    "users",
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
