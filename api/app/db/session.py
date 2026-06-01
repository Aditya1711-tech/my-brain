from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=(not settings.is_production),
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=280,
    # Required when DATABASE_URL points to Supabase transaction pooler (port 6543).
    # Supavisor in transaction mode doesn't support named prepared statements.
    connect_args={"statement_cache_size": 0},
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async DB session."""
    async with async_session_factory() as session:
        yield session
