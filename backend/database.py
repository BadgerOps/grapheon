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
        "hosts",
        [
            ("vlan_id", "vlan_id INTEGER"),
            ("vlan_name", "vlan_name VARCHAR(32)"),
        ],
    )
    _ensure_columns(
        sync_conn,
        "raw_imports",
        [
            ("source_host", "source_host VARCHAR(255)"),
        ],
    )

    # DeviceIdentity: link multi-homed hosts to the same physical device
    _ensure_columns(
        sync_conn,
        "hosts",
        [
            ("device_id", "device_id INTEGER"),
        ],
    )

    # Migrate connections table: make remote_port nullable (for LISTEN state)
    _make_column_nullable(sync_conn, "connections", "remote_port")


def _ensure_columns(sync_conn, table: str, columns: list[tuple[str, str]]) -> None:
    existing = [
        row[1]
        for row in sync_conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    ]
    for column_name, ddl in columns:
        if column_name not in existing:
            sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def _make_column_nullable(sync_conn, table: str, column: str) -> None:
    """SQLite: recreate table to change a column from NOT NULL to nullable."""
    rows = sync_conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    col_info = None
    for row in rows:
        if row[1] == column:
            col_info = row
            break
    if col_info is None:
        return  # column doesn't exist
    # col_info: (cid, name, type, notnull, dflt_value, pk)
    if col_info[3] == 0:
        return  # already nullable, nothing to do

    # Build column definitions for the new table
    col_defs = []
    for row in rows:
        cid, name, dtype, notnull, dflt, pk = row
        parts = [f'"{name}"', dtype or "TEXT"]
        if pk:
            parts.append("PRIMARY KEY")
        if notnull and name != column:
            parts.append("NOT NULL")
        if dflt is not None:
            parts.append(f"DEFAULT {dflt}")
        col_defs.append(" ".join(parts))

    col_names = ", ".join(f'"{r[1]}"' for r in rows)
    tmp = f"{table}__migrate_tmp"

    sync_conn.execute(text(f"CREATE TABLE {tmp} ({', '.join(col_defs)})"))
    sync_conn.execute(text(f"INSERT INTO {tmp} ({col_names}) SELECT {col_names} FROM {table}"))
    sync_conn.execute(text(f"DROP TABLE {table}"))
    sync_conn.execute(text(f"ALTER TABLE {tmp} RENAME TO {table}"))

    # Recreate indexes
    if table == "connections":
        for idx_name, idx_col in [
            ("idx_connection_local_ip", "local_ip"),
            ("idx_connection_remote_ip", "remote_ip"),
            ("idx_connection_protocol", "protocol"),
            ("idx_connection_state", "state"),
        ]:
            sync_conn.execute(text(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ("{idx_col}")'))



async def close_db():
    """Close database connection."""
    await engine.dispose()
