from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import settings

# .env stores a bare postgresql:// URL (shared with the academy project); the
# async driver is chosen here so the DSN stays provider-agnostic. psycopg is
# used rather than asyncpg because the DSN carries libpq params (sslmode=...).
dsn = make_url(settings.database_url).set(drivername="postgresql+psycopg")

engine = create_async_engine(dsn, pool_pre_ping=True, future=True)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
