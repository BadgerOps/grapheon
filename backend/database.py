from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy import text
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator

from config import settings

# Ensure data directory exists
db_path = settings.DATABASE_URL.replace("sqlite:///", "")
if db_path.startswith("./"):
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///"),
    echo=False,
    future=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    future=True,
)

# Declarative base for models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_migrations)


def _run_migrations(sync_conn) -> None:
    """Apply lightweight migrations for new columns."""
    _ensure_columns(
        sync_conn,
        "hosts",
        [
            ("guid", "guid VARCHAR(36)"),
        ],
    )
    _ensure_columns(
        sync_conn,
        "arp_entries",
        [
            ("entry_type", "entry_type VARCHAR(50)"),
            ("vendor", "vendor VARCHAR(255)"),
        ],
    )
    _ensure_columns(
        sync_conn,
        "raw_imports",
        [
            ("source_host", "source_host VARCHAR(255)"),
        ],
    )


def _ensure_columns(sync_conn, table: str, columns: list[tuple[str, str]]) -> None:
    existing = [
        row[1]
        for row in sync_conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    ]
    for column_name, ddl in columns:
        if column_name not in existing:
            sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


async def close_db():
    """Close database connection."""
    await engine.dispose()
