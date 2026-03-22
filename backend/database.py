import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy import event, text
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator

from config import settings

logger = logging.getLogger(__name__)

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


# ── SQLite performance pragmas ────────────────────────────────────────
# Applied on every new connection so they survive connection recycling.

@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    # WAL mode: allows concurrent readers while a writer is active
    cursor.execute("PRAGMA journal_mode=WAL")
    # NORMAL sync is safe with WAL and avoids fsync on every commit
    cursor.execute("PRAGMA synchronous=NORMAL")
    # 64 MB page cache (negative value = KiB)
    cursor.execute("PRAGMA cache_size=-65536")
    # 5 s busy timeout — retry on SQLITE_BUSY instead of failing instantly
    cursor.execute("PRAGMA busy_timeout=5000")
    # Store temp tables in memory
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.close()
    logger.debug("SQLite pragmas applied (WAL, sync=NORMAL, cache=64MB, busy=5s)")

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
            ("stored_file_path", "stored_file_path VARCHAR(1024)"),
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
    _make_column_nullable(sync_conn, "raw_imports", "raw_data")

    _ensure_columns(
        sync_conn,
        "agents",
        [
            ("enrollment_key_id", "enrollment_key_id INTEGER"),
            ("approval_required", "approval_required BOOLEAN DEFAULT 1"),
            ("api_key_hash", "api_key_hash VARCHAR(64)"),
            ("api_key_prefix", "api_key_prefix VARCHAR(32)"),
            ("approved_at", "approved_at DATETIME"),
            ("rejected_at", "rejected_at DATETIME"),
            ("api_key_issued_at", "api_key_issued_at DATETIME"),
            ("last_registration_at", "last_registration_at DATETIME"),
            ("last_mac_addresses", "last_mac_addresses JSON"),
            ("last_registration_summary", "last_registration_summary JSON"),
        ],
    )
    _ensure_columns(
        sync_conn,
        "agent_checkins",
        [
            ("auth_method", "auth_method VARCHAR(50)"),
            ("api_key_prefix", "api_key_prefix VARCHAR(32)"),
        ],
    )
    _create_index_if_missing(sync_conn, "idx_agent_enrollment_key_id", "agents", "enrollment_key_id")
    _create_index_if_missing(sync_conn, "idx_agent_api_key_hash", "agents", "api_key_hash")
    _create_index_if_missing(sync_conn, "idx_agent_api_key_prefix", "agents", "api_key_prefix")
    _create_index_if_missing(sync_conn, "idx_agent_enrollment_key_is_active", "agent_enrollment_keys", "is_active")
    _create_index_if_missing(sync_conn, "idx_agent_enrollment_key_default_policy_id", "agent_enrollment_keys", "default_policy_id")
    _create_index_if_missing(sync_conn, "idx_agent_checkin_api_key_prefix", "agent_checkins", "api_key_prefix")


def _ensure_columns(sync_conn, table: str, columns: list[tuple[str, str]]) -> None:
    rows = sync_conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    if not rows:
        return
    existing = [row[1] for row in rows]
    for column_name, ddl in columns:
        if column_name not in existing:
            sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def _create_index_if_missing(sync_conn, index_name: str, table: str, column: str) -> None:
    rows = sync_conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    if not rows:
        return
    sync_conn.execute(
        text(f'CREATE INDEX IF NOT EXISTS {index_name} ON {table} ("{column}")')
    )


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
