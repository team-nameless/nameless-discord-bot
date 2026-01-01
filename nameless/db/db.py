from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_async_session: async_sessionmaker[AsyncSession] | None = None


async def init(database_url: str | None = None, filename: str | None = None) -> None:
    if not database_url:
        if not filename:
            filename = "nameless.db"
        database_url = f"sqlite+aiosqlite:///{filename}"

    global _engine, _async_session
    if _engine is not None:
        logger.debug("Database engine already initialized")
        return

    logger.info("Initializing database engine")
    _engine = create_async_engine(database_url, echo=False, future=True)
    _async_session = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)

    # Create tables if using simple dev DB; migrations recommended for production
    await create_tables()


async def dispose() -> None:
    global _engine, _async_session
    if _engine is None:
        logger.debug("Dispose called but engine is not initialized")
        return

    logger.info("Disposing database engine")
    await _engine.dispose()
    _engine = None
    _async_session = None


@asynccontextmanager
async def get_session_context(*, commit: bool = True):
    if _async_session is None:
        raise RuntimeError("Database not initialized; call init(database_url) first")

    async with _async_session() as session:
        yield session

        if not commit:
            # await session.flush()
            return

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    if _engine is None:
        raise RuntimeError("Database not initialized; call init(database_url) first")
    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
