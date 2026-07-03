"""Async database connection and session management using SQLAlchemy."""

from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.models.database import Base
from app.utils.logger import logger

# Ensure the data directory exists for the SQLite file
_db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

# Async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,  # Set True for SQL query logging during debugging
    future=True,
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all database tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized successfully")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session (FastAPI dependency)."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_db() -> None:
    """Dispose of the database engine on shutdown."""
    await engine.dispose()
    logger.info("Database connection closed")
