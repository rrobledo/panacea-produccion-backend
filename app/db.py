from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        # Vercel's serverless model is stateless/cold-start, so this engine is
        # not held across invocations — it's created fresh per cold start and
        # relies on the connection string pointing at a pooled endpoint
        # (Neon/Vercel Postgres "-pooler"), not a direct connection.
        _engine = create_async_engine(
            settings.sqlalchemy_database_url,
            pool_pre_ping=True,
            connect_args={"ssl": "require"},
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
