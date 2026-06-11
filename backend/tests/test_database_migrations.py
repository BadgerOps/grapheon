from sqlalchemy import create_engine, text

from database import _run_migrations


def test_agent_observer_metadata_migration_backfills_legacy_rows(tmp_path):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE agents (
                    id INTEGER PRIMARY KEY,
                    agent_uuid VARCHAR(128),
                    enrollment_state VARCHAR(20),
                    is_active BOOLEAN
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE hosts (
                    id INTEGER PRIMARY KEY,
                    ip_address VARCHAR(45),
                    source_types JSON
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE raw_imports (
                    id INTEGER PRIMARY KEY,
                    source_type VARCHAR(50),
                    import_type VARCHAR(50)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE arp_entries (
                    id INTEGER PRIMARY KEY,
                    ip_address VARCHAR(45),
                    mac_address VARCHAR(17),
                    source_type VARCHAR(50)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE connections (
                    id INTEGER PRIMARY KEY,
                    local_ip VARCHAR(45),
                    local_port INTEGER,
                    remote_ip VARCHAR(45),
                    remote_port INTEGER NOT NULL,
                    protocol VARCHAR(10),
                    state VARCHAR(50),
                    source_type VARCHAR(50)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE agent_observations (
                    id INTEGER PRIMARY KEY,
                    agent_id INTEGER NOT NULL,
                    raw_import_id INTEGER,
                    last_seen_checkin_id INTEGER,
                    observation_type VARCHAR(32) NOT NULL,
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
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )

        conn.execute(text("INSERT INTO agents (id, agent_uuid, enrollment_state, is_active) VALUES (1, 'agent-1', 'active', 1)"))
        conn.execute(text("INSERT INTO hosts (id, ip_address, source_types) VALUES (10, '10.1.0.5', '[\"agent\"]')"))
        conn.execute(text("INSERT INTO hosts (id, ip_address, source_types) VALUES (11, '10.1.0.1', '[\"agent\"]')"))
        conn.execute(text("INSERT INTO raw_imports (id, source_type, import_type) VALUES (100, 'agent', 'agent')"))
        conn.execute(text("INSERT INTO arp_entries (id, ip_address, mac_address, source_type) VALUES (20, '10.1.0.1', 'AA:BB:CC:00:00:01', 'agent')"))
        conn.execute(text("INSERT INTO connections (id, local_ip, local_port, remote_ip, remote_port, protocol, state, source_type) VALUES (30, '10.1.0.5', 443, '10.1.0.10', 51514, 'tcp', 'established', 'agent')"))
        conn.execute(
            text(
                """
                INSERT INTO agent_observations (
                    id, agent_id, raw_import_id, observation_type, identity_hash, payload,
                    host_id, arp_entry_id, connection_id, first_seen_at, last_seen_at,
                    is_current, created_at, updated_at
                )
                VALUES
                    (1, 1, 100, 'address', 'hash-address', '{}', 10, NULL, NULL, '2026-06-11 00:00:00', '2026-06-11 00:00:00', 1, '2026-06-11 00:00:00', '2026-06-11 00:00:00'),
                    (2, 1, 100, 'neighbor', 'hash-neighbor', '{}', 11, 20, NULL, '2026-06-11 00:00:00', '2026-06-11 00:00:00', 1, '2026-06-11 00:00:00', '2026-06-11 00:00:00'),
                    (3, 1, 100, 'connection', 'hash-connection', '{}', 10, NULL, 30, '2026-06-11 00:00:00', '2026-06-11 00:00:00', 1, '2026-06-11 00:00:00', '2026-06-11 00:00:00'),
                    (4, 1, 100, 'route', 'hash-route', '{}', 10, NULL, NULL, '2026-06-11 00:00:00', '2026-06-11 00:00:00', 1, '2026-06-11 00:00:00', '2026-06-11 00:00:00')
                """
            )
        )

        _run_migrations(conn)

        columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(agent_observations)")).fetchall()
        }
        assert {
            "observation_role",
            "confidence",
            "relationship_type",
            "relationship_key",
        }.issubset(columns)

        rows = conn.execute(
            text(
                """
                SELECT observation_type, observation_role, confidence, relationship_type, relationship_key
                FROM agent_observations
                ORDER BY id
                """
            )
        ).fetchall()
        assert rows == [
            ("address", "agent_self_interface", 95, "collector_interface", "hash-address"),
            ("neighbor", "arp_neighbor", 80, "arp_neighbor", "hash-neighbor"),
            ("connection", "connection_remote", 35, "connection_remote", "hash-connection"),
            ("route", "route_gateway", 70, "route_gateway", "hash-route"),
        ]

        hosts = conn.execute(
            text("SELECT id, observed_by_agent_ids FROM hosts ORDER BY id")
        ).fetchall()
        assert hosts == [(10, "[1]"), (11, "[1]")]

        arp_observer = conn.execute(
            text("SELECT observer_agent_id FROM arp_entries WHERE id = 20")
        ).scalar_one()
        assert arp_observer == 1

        connection_observer = conn.execute(
            text("SELECT observer_agent_id FROM connections WHERE id = 30")
        ).scalar_one()
        assert connection_observer == 1

        evidence_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(entity_evidence)")).fetchall()
        }
        assert {
            "entity_type",
            "entity_id",
            "field_name",
            "observed_value",
            "source_origin",
            "source_type",
            "observer_agent_id",
            "raw_import_id",
            "agent_observation_id",
            "relationship_type",
            "confidence",
            "metadata",
        }.issubset(evidence_columns)
        evidence_indexes = {
            row[1]
            for row in conn.execute(text("PRAGMA index_list(entity_evidence)")).fetchall()
        }
        assert "idx_entity_evidence_entity" in evidence_indexes
        assert "idx_entity_evidence_field" in evidence_indexes

        network_group_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(network_groups)")).fetchall()
        }
        assert {
            "cidr",
            "label",
            "description",
            "source",
            "confidence",
            "is_expected",
            "is_hidden",
            "metadata",
        }.issubset(network_group_columns)
        network_group_indexes = {
            row[1]
            for row in conn.execute(text("PRAGMA index_list(network_groups)")).fetchall()
        }
        assert "idx_network_groups_cidr" in network_group_indexes
        assert "idx_network_groups_hidden" in network_group_indexes

        raw_origin = conn.execute(
            text("SELECT source_origin FROM raw_imports WHERE id = 100")
        ).scalar_one()
        assert raw_origin == "agent"
