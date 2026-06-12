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
            ("source_origin", "source_origin VARCHAR(50) DEFAULT 'manual'"),
        ],
    )
    _ensure_columns(
        sync_conn,
        "hosts",
        [
            ("source_origins", "source_origins JSON"),
            ("observed_by_agent_ids", "observed_by_agent_ids JSON"),
        ],
    )
    _ensure_columns(
        sync_conn,
        "ports",
        [
            ("source_origins", "source_origins JSON"),
        ],
    )
    _ensure_columns(
        sync_conn,
        "arp_entries",
        [
            ("source_origin", "source_origin VARCHAR(50)"),
            ("observer_agent_id", "observer_agent_id INTEGER"),
        ],
    )
    _ensure_columns(
        sync_conn,
        "connections",
        [
            ("source_origin", "source_origin VARCHAR(50)"),
            ("observer_agent_id", "observer_agent_id INTEGER"),
        ],
    )
    _backfill_source_origins(sync_conn)

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
            ("collection_requested_at", "collection_requested_at DATETIME"),
            ("collection_request_reason", "collection_request_reason VARCHAR(1000)"),
            ("collection_request_options", "collection_request_options JSON"),
            ("collection_request_fulfilled_at", "collection_request_fulfilled_at DATETIME"),
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
    _create_agent_observations_table(sync_conn)
    _ensure_columns(
        sync_conn,
        "agent_observations",
        [
            ("observation_role", "observation_role VARCHAR(64)"),
            ("confidence", "confidence INTEGER DEFAULT 50"),
            ("relationship_type", "relationship_type VARCHAR(64)"),
            ("relationship_key", "relationship_key VARCHAR(255)"),
        ],
    )
    _create_index_if_missing(sync_conn, "idx_arp_entries_observer_agent_id", "arp_entries", "observer_agent_id")
    _create_index_if_missing(sync_conn, "idx_connections_observer_agent_id", "connections", "observer_agent_id")
    _create_index_if_missing(sync_conn, "idx_agent_observations_role", "agent_observations", "observation_role")
    _create_index_if_missing(sync_conn, "idx_agent_observations_confidence", "agent_observations", "confidence")
    _create_index_if_missing(sync_conn, "idx_agent_observations_relationship_type", "agent_observations", "relationship_type")
    _create_index_if_missing(sync_conn, "idx_agent_observations_relationship_key", "agent_observations", "relationship_key")
    _create_entity_evidence_table(sync_conn)
    _create_network_groups_table(sync_conn)
    _backfill_agent_observer_metadata(sync_conn)


def _backfill_source_origins(sync_conn) -> None:
    """Populate source-origin columns for databases created before the field existed."""
    sync_conn.execute(
        text(
            """
            UPDATE raw_imports
            SET source_origin = CASE
                WHEN source_type = 'agent' OR import_type = 'agent' THEN 'agent'
                ELSE 'manual'
            END
            WHERE source_origin IS NULL
               OR (
                   source_origin = 'manual'
                   AND (source_type = 'agent' OR import_type = 'agent')
               )
            """
        )
    )
    for table in ("hosts", "ports"):
        rows = sync_conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        columns = {row[1] for row in rows}
        if "source_origins" not in columns:
            continue
        sync_conn.execute(
            text(
                f"""
                UPDATE {table}
                SET source_origins = CASE
                    WHEN source_types LIKE '%"agent"%' AND source_types != '["agent"]'
                        THEN '["manual","agent"]'
                    WHEN source_types LIKE '%"agent"%'
                        THEN '["agent"]'
                    ELSE '["manual"]'
                END
                WHERE source_origins IS NULL
                """
            )
        )
    for table in ("arp_entries", "connections"):
        rows = sync_conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        columns = {row[1] for row in rows}
        if "source_origin" not in columns:
            continue
        sync_conn.execute(
            text(
                f"""
                UPDATE {table}
                SET source_origin = CASE
                    WHEN source_type = 'agent' THEN 'agent'
                    ELSE 'manual'
                END
                WHERE source_origin IS NULL
                """
            )
        )


def _backfill_agent_observer_metadata(sync_conn) -> None:
    """Populate observer/vantage metadata for databases created before the fields existed."""
    rows = sync_conn.execute(text("PRAGMA table_info(agent_observations)")).fetchall()
    columns = {row[1] for row in rows}
    if {
        "observation_role",
        "confidence",
        "relationship_type",
        "relationship_key",
    }.issubset(columns):
        sync_conn.execute(
            text(
                """
                UPDATE agent_observations
                SET
                    observation_role = CASE observation_type
                        WHEN 'address' THEN 'agent_self_interface'
                        WHEN 'neighbor' THEN 'arp_neighbor'
                        WHEN 'connection' THEN 'connection_remote'
                        WHEN 'route' THEN 'route_gateway'
                        ELSE observation_type
                    END,
                    confidence = CASE observation_type
                        WHEN 'address' THEN 95
                        WHEN 'neighbor' THEN 80
                        WHEN 'connection' THEN 35
                        WHEN 'route' THEN 70
                        ELSE 50
                    END,
                    relationship_type = CASE observation_type
                        WHEN 'address' THEN 'collector_interface'
                        WHEN 'neighbor' THEN 'arp_neighbor'
                        WHEN 'connection' THEN 'connection_remote'
                        WHEN 'route' THEN 'route_gateway'
                        ELSE NULL
                    END,
                    relationship_key = COALESCE(relationship_key, identity_hash)
                WHERE observation_role IS NULL
                   OR confidence IS NULL
                   OR relationship_key IS NULL
                """
            )
        )

    rows = sync_conn.execute(text("PRAGMA table_info(hosts)")).fetchall()
    columns = {row[1] for row in rows}
    if "observed_by_agent_ids" in columns:
        sync_conn.execute(
            text(
                """
                UPDATE hosts
                SET observed_by_agent_ids = (
                    SELECT '[' || group_concat(DISTINCT agent_id) || ']'
                    FROM agent_observations
                    WHERE agent_observations.host_id = hosts.id
                )
                WHERE observed_by_agent_ids IS NULL
                  AND EXISTS (
                    SELECT 1
                    FROM agent_observations
                    WHERE agent_observations.host_id = hosts.id
                  )
                """
            )
        )

    rows = sync_conn.execute(text("PRAGMA table_info(arp_entries)")).fetchall()
    columns = {row[1] for row in rows}
    if "observer_agent_id" in columns:
        sync_conn.execute(
            text(
                """
                UPDATE arp_entries
                SET observer_agent_id = (
                    SELECT agent_id
                    FROM agent_observations
                    WHERE agent_observations.arp_entry_id = arp_entries.id
                    ORDER BY last_seen_at DESC
                    LIMIT 1
                )
                WHERE observer_agent_id IS NULL
                  AND EXISTS (
                    SELECT 1
                    FROM agent_observations
                    WHERE agent_observations.arp_entry_id = arp_entries.id
                  )
                """
            )
        )

    rows = sync_conn.execute(text("PRAGMA table_info(connections)")).fetchall()
    columns = {row[1] for row in rows}
    if "observer_agent_id" in columns:
        sync_conn.execute(
            text(
                """
                UPDATE connections
                SET observer_agent_id = (
                    SELECT agent_id
                    FROM agent_observations
                    WHERE agent_observations.connection_id = connections.id
                    ORDER BY last_seen_at DESC
                    LIMIT 1
                )
                WHERE observer_agent_id IS NULL
                  AND EXISTS (
                    SELECT 1
                    FROM agent_observations
                    WHERE agent_observations.connection_id = connections.id
                  )
                """
            )
        )


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


def _create_agent_observations_table(sync_conn) -> None:
    sync_conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS agent_observations (
                id INTEGER PRIMARY KEY,
                agent_id INTEGER NOT NULL,
                raw_import_id INTEGER,
                last_seen_checkin_id INTEGER,
                observation_type VARCHAR(32) NOT NULL,
                observation_role VARCHAR(64),
                confidence INTEGER NOT NULL DEFAULT 50,
                relationship_type VARCHAR(64),
                relationship_key VARCHAR(255),
                identity_hash VARCHAR(64) NOT NULL,
                payload JSON NOT NULL,
                host_id INTEGER,
                arp_entry_id INTEGER,
                connection_id INTEGER,
                first_seen_at DATETIME NOT NULL,
                last_seen_at DATETIME NOT NULL,
                stale_at DATETIME,
                removed_at DATETIME,
                is_current BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                UNIQUE (agent_id, observation_type, identity_hash),
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE,
                FOREIGN KEY(raw_import_id) REFERENCES raw_imports(id) ON DELETE SET NULL,
                FOREIGN KEY(last_seen_checkin_id) REFERENCES agent_checkins(id) ON DELETE SET NULL,
                FOREIGN KEY(host_id) REFERENCES hosts(id) ON DELETE SET NULL,
                FOREIGN KEY(arp_entry_id) REFERENCES arp_entries(id) ON DELETE SET NULL,
                FOREIGN KEY(connection_id) REFERENCES connections(id) ON DELETE SET NULL
            )
            """
        )
    )
    _ensure_columns(
        sync_conn,
        "agent_observations",
        [
            ("observation_role", "observation_role VARCHAR(64)"),
            ("confidence", "confidence INTEGER DEFAULT 50"),
            ("relationship_type", "relationship_type VARCHAR(64)"),
            ("relationship_key", "relationship_key VARCHAR(255)"),
        ],
    )
    for index_name, column in [
        ("idx_agent_observations_agent_id", "agent_id"),
        ("idx_agent_observations_raw_import_id", "raw_import_id"),
        ("idx_agent_observations_checkin_id", "last_seen_checkin_id"),
        ("idx_agent_observations_type", "observation_type"),
        ("idx_agent_observations_role", "observation_role"),
        ("idx_agent_observations_confidence", "confidence"),
        ("idx_agent_observations_relationship_type", "relationship_type"),
        ("idx_agent_observations_relationship_key", "relationship_key"),
        ("idx_agent_observations_identity", "identity_hash"),
        ("idx_agent_observations_host_id", "host_id"),
        ("idx_agent_observations_arp_entry_id", "arp_entry_id"),
        ("idx_agent_observations_connection_id", "connection_id"),
        ("idx_agent_observations_current", "is_current"),
    ]:
        sync_conn.execute(
            text(f'CREATE INDEX IF NOT EXISTS {index_name} ON agent_observations ("{column}")')
        )


def _create_entity_evidence_table(sync_conn) -> None:
    sync_conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS entity_evidence (
                id INTEGER PRIMARY KEY,
                entity_type VARCHAR(50) NOT NULL,
                entity_id INTEGER NOT NULL,
                field_name VARCHAR(100),
                observed_value TEXT,
                source_origin VARCHAR(50) NOT NULL,
                source_type VARCHAR(50),
                observer_agent_id INTEGER,
                raw_import_id INTEGER,
                agent_observation_id INTEGER,
                relationship_type VARCHAR(64),
                confidence INTEGER NOT NULL DEFAULT 50,
                first_seen_at DATETIME NOT NULL,
                last_seen_at DATETIME NOT NULL,
                is_current BOOLEAN NOT NULL DEFAULT 1,
                metadata JSON,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY(observer_agent_id) REFERENCES agents(id) ON DELETE SET NULL,
                FOREIGN KEY(raw_import_id) REFERENCES raw_imports(id) ON DELETE SET NULL,
                FOREIGN KEY(agent_observation_id) REFERENCES agent_observations(id) ON DELETE SET NULL
            )
            """
        )
    )
    for index_name, column in [
        ("idx_entity_evidence_entity_type", "entity_type"),
        ("idx_entity_evidence_entity_id", "entity_id"),
        ("idx_entity_evidence_field_name", "field_name"),
        ("idx_entity_evidence_source_origin", "source_origin"),
        ("idx_entity_evidence_source_type", "source_type"),
        ("idx_entity_evidence_observer_agent_id", "observer_agent_id"),
        ("idx_entity_evidence_raw_import_id", "raw_import_id"),
        ("idx_entity_evidence_agent_observation_id", "agent_observation_id"),
        ("idx_entity_evidence_relationship_type", "relationship_type"),
        ("idx_entity_evidence_confidence", "confidence"),
        ("idx_entity_evidence_is_current", "is_current"),
    ]:
        sync_conn.execute(
            text(f'CREATE INDEX IF NOT EXISTS {index_name} ON entity_evidence ("{column}")')
        )
    sync_conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_entity_evidence_entity "
            'ON entity_evidence ("entity_type", "entity_id")'
        )
    )
    sync_conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_entity_evidence_field "
            'ON entity_evidence ("entity_type", "entity_id", "field_name")'
        )
    )


def _create_network_groups_table(sync_conn) -> None:
    sync_conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS network_groups (
                id INTEGER PRIMARY KEY,
                cidr VARCHAR(64) NOT NULL UNIQUE,
                label VARCHAR(255),
                description TEXT,
                source VARCHAR(50) NOT NULL DEFAULT 'manual',
                confidence INTEGER NOT NULL DEFAULT 100,
                is_expected BOOLEAN NOT NULL DEFAULT 1,
                is_hidden BOOLEAN NOT NULL DEFAULT 0,
                metadata JSON,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
    )
    for index_name, column in [
        ("idx_network_groups_cidr", "cidr"),
        ("idx_network_groups_source", "source"),
        ("idx_network_groups_expected", "is_expected"),
        ("idx_network_groups_hidden", "is_hidden"),
    ]:
        sync_conn.execute(
            text(f'CREATE INDEX IF NOT EXISTS {index_name} ON network_groups ("{column}")')
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
