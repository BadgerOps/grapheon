import gzip
import json
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from config import settings
from database import get_db
from main import app
from models import (
    ARPEntry,
    Agent,
    AgentCheckIn,
    AgentEnrollmentKey,
    Connection,
    Host,
    RawImport,
)


async def _create_policy(async_client: AsyncClient, headers, name: str) -> int:
    response = await async_client.post(
        "/api/agents/policies",
        json={
            "name": name,
            "description": f"Policy for {name}",
            "checkin_interval_seconds": 1800,
            "jitter_seconds": 60,
            "command_timeout_seconds": 15,
            "enabled_commands": {
                "ip_neigh": True,
                "ss_tunap": True,
                "ip_addr": True,
                "ip_route": True,
            },
            "max_report_bytes": 262144,
            "is_active": True,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_enrollment_key(
    async_client: AsyncClient,
    headers,
    name: str,
    policy_id: int,
    *,
    auto_approve: bool = True,
    is_active: bool = True,
    expires_at: str | None = None,
    max_registrations: int | None = None,
) -> str:
    response = await async_client.post(
        "/api/agents/enrollment-keys",
        json={
            "name": name,
            "description": f"Enrollment key for {name}",
            "default_policy_id": policy_id,
            "auto_approve": auto_approve,
            "is_active": is_active,
            "expires_at": expires_at,
            "max_registrations": max_registrations,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["enrollment_key"]


async def _register_agent(
    async_client: AsyncClient,
    enrollment_key: str,
    agent_uuid: str,
    *,
    ip_address: str = "10.70.0.5",
    mac_address: str = "AA:BB:CC:70:00:05",
):
    return await async_client.post(
        "/api/agents/register",
        json={
            "enrollment_key": enrollment_key,
            "agent_uuid": agent_uuid,
            "display_name": agent_uuid,
            "hostname": f"{agent_uuid}.test.local",
            "site_name": "Test",
            "agent_version": "0.1.0",
            "platform": "linux",
            "platform_release": "6.12",
            "addresses": [
                {
                    "ip_address": ip_address,
                    "interface": "eth0",
                    "prefix_length": 24,
                    "mac_address": mac_address,
                }
            ],
        },
    )


def _checkin_payload(agent_uuid: str, *, observed_at: str = "2026-03-22T20:00:00Z"):
    return {
        "agent_uuid": agent_uuid,
        "observed_at": observed_at,
        "sequence_number": 1,
        "full_snapshot": False,
        "hostname": f"{agent_uuid}.test.local",
        "agent_version": "0.1.0",
        "platform": "linux",
        "platform_release": "6.12",
        "addresses": [
            {
                "ip_address": "10.70.0.5",
                "interface": "eth0",
                "prefix_length": 24,
                "mac_address": "AA:BB:CC:70:00:05",
            }
        ],
        "neighbors": [],
        "connections": [],
        "routes": [],
    }


async def _post_checkin(async_client: AsyncClient, api_key: str, payload: dict):
    return await async_client.post(
        "/api/agents/check-in",
        content=gzip.compress(json.dumps(payload).encode("utf-8")),
        headers={
            settings.AGENT_API_KEY_HEADER: api_key,
            "Content-Encoding": "gzip",
            "Content-Type": "application/json",
        },
    )


class TestAgentEnrollmentAndCheckIn:
    @pytest.mark.asyncio
    async def test_create_enrollment_key_and_pending_registration(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        headers = await auth_headers("admin", "agent_admin")

        policy_response = await async_client.post(
            "/api/agents/policies",
            json={
                "name": "hourly-passive",
                "description": "Low impact hourly collection",
                "checkin_interval_seconds": 3600,
                "jitter_seconds": 300,
                "command_timeout_seconds": 20,
                "enabled_commands": {
                    "ip_neigh": True,
                    "ss_tunap": True,
                    "ip_addr": True,
                    "ip_route": False,
                },
                "max_report_bytes": 262144,
                "is_active": True,
            },
            headers=headers,
        )
        assert policy_response.status_code == 201
        policy_id = policy_response.json()["id"]

        enrollment_response = await async_client.post(
            "/api/agents/enrollment-keys",
            json={
                "name": "branch-offices",
                "description": "Manual approval required for branch sites",
                "default_policy_id": policy_id,
                "auto_approve": False,
                "is_active": True,
                "max_registrations": 10,
            },
            headers=headers,
        )
        assert enrollment_response.status_code == 201
        enrollment_data = enrollment_response.json()
        enrollment_key = enrollment_data["enrollment_key"]
        assert enrollment_data["key"]["default_policy"]["id"] == policy_id

        register_response = await async_client.post(
            "/api/agents/register",
            json={
                "enrollment_key": enrollment_key,
                "agent_uuid": "agent-001",
                "display_name": "Branch router",
                "hostname": "branch-router-01",
                "site_name": "Boise",
                "agent_version": "0.1.0",
                "platform": "linux",
                "platform_release": "6.12",
                "addresses": [
                    {
                        "ip_address": "10.10.0.5",
                        "interface": "eth0",
                        "prefix_length": 24,
                        "mac_address": "AA:BB:CC:DD:EE:01",
                    }
                ],
            },
        )
        assert register_response.status_code == 200
        register_data = register_response.json()
        assert register_data["status"] == "pending"
        assert register_data["approval_required"] is True
        assert register_data["api_key"] is None
        assert register_data["agent"]["enrollment_state"] == "pending"
        assert register_data["agent"]["policy"]["id"] == policy_id

        list_response = await async_client.get("/api/agents", headers=headers)
        assert list_response.status_code == 200
        list_data = list_response.json()
        assert list_data["total"] == 1
        assert list_data["items"][0]["agent_uuid"] == "agent-001"
        assert list_data["items"][0]["enrollment_state"] == "pending"

        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()
        assert (
            await db.execute(select(func.count(AgentEnrollmentKey.id)))
        ).scalar_one() == 1

    @pytest.mark.asyncio
    async def test_approval_then_api_key_checkin_ingests_and_deduplicates(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        admin_headers = await auth_headers("admin", "agent_checkin_admin")

        policy_response = await async_client.post(
            "/api/agents/policies",
            json={
                "name": "agent-default",
                "description": "Default passive check-in policy",
                "checkin_interval_seconds": 1800,
                "jitter_seconds": 120,
                "command_timeout_seconds": 15,
                "enabled_commands": {
                    "ip_neigh": True,
                    "ss_tunap": True,
                    "ip_addr": True,
                    "ip_route": True,
                },
                "max_report_bytes": 262144,
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert policy_response.status_code == 201
        policy_id = policy_response.json()["id"]

        enrollment_response = await async_client.post(
            "/api/agents/enrollment-keys",
            json={
                "name": "lab-enrollment",
                "description": "Pending approval for lab agents",
                "default_policy_id": policy_id,
                "auto_approve": False,
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert enrollment_response.status_code == 201
        enrollment_key = enrollment_response.json()["enrollment_key"]

        register_payload = {
            "enrollment_key": enrollment_key,
            "agent_uuid": "agent-002",
            "display_name": "Passive collector",
            "hostname": "collector-01",
            "site_name": "Lab",
            "agent_version": "0.1.0",
            "platform": "linux",
            "platform_release": "6.12",
            "metadata": {"collector": "systemd-timer"},
            "addresses": [
                {
                    "ip_address": "10.0.0.5",
                    "interface": "eth0",
                    "prefix_length": 24,
                    "mac_address": "AA:BB:CC:DD:EE:FF",
                }
            ],
        }

        initial_register = await async_client.post(
            "/api/agents/register",
            json=register_payload,
        )
        assert initial_register.status_code == 200
        assert initial_register.json()["status"] == "pending"
        agent_id = initial_register.json()["agent"]["id"]

        approve_response = await async_client.post(
            f"/api/agents/{agent_id}/approve",
            json={"policy_id": policy_id},
            headers=admin_headers,
        )
        assert approve_response.status_code == 200
        assert approve_response.json()["enrollment_state"] == "active"

        approved_register = await async_client.post(
            "/api/agents/register",
            json=register_payload,
        )
        assert approved_register.status_code == 200
        approved_data = approved_register.json()
        assert approved_data["status"] == "active"
        assert approved_data["approval_required"] is False
        assert approved_data["api_key"]
        api_key = approved_data["api_key"]

        base_payload = {
            "agent_uuid": "agent-002",
            "observed_at": "2026-03-22T18:00:00Z",
            "sequence_number": 1,
            "full_snapshot": False,
            "hostname": "collector-01",
            "agent_version": "0.1.0",
            "platform": "linux",
            "platform_release": "6.12",
            "metadata": {"collector": "systemd-timer"},
            "addresses": [
                {
                    "ip_address": "10.0.0.5",
                    "interface": "eth0",
                    "prefix_length": 24,
                    "mac_address": "AA:BB:CC:DD:EE:FF",
                }
            ],
            "neighbors": [
                {
                    "ip_address": "10.0.0.1",
                    "mac_address": "11:22:33:44:55:66",
                    "interface": "eth0",
                    "state": "reachable",
                }
            ],
            "connections": [
                {
                    "local_ip": "10.0.0.5",
                    "local_port": 443,
                    "remote_ip": "10.0.0.10",
                    "remote_port": 51514,
                    "protocol": "tcp",
                    "state": "established",
                    "pid": 777,
                    "process_name": "python",
                }
            ],
            "routes": [
                {
                    "destination": "default",
                    "gateway": "10.0.0.1",
                    "interface": "eth0",
                    "source_ip": "10.0.0.5",
                }
            ],
        }

        checkin_headers = {
            settings.AGENT_API_KEY_HEADER: api_key,
            "Content-Encoding": "gzip",
            "Content-Type": "application/json",
        }

        first_response = await async_client.post(
            "/api/agents/check-in",
            content=gzip.compress(json.dumps(base_payload).encode("utf-8")),
            headers=checkin_headers,
        )
        assert first_response.status_code == 200
        first_data = first_response.json()
        assert first_data["status"] == "accepted"
        assert first_data["summary"]["hosts_created"] == 3
        assert first_data["summary"]["arp_entries_created"] == 1
        assert first_data["summary"]["connections_created"] == 1
        assert first_data["policy"]["id"] == policy_id
        assert first_data["checkin"]["auth_method"] == "api_key"

        second_payload = dict(base_payload)
        second_payload["sequence_number"] = 2
        second_payload["observed_at"] = "2026-03-22T18:30:00Z"

        second_response = await async_client.post(
            "/api/agents/check-in",
            content=gzip.compress(json.dumps(second_payload).encode("utf-8")),
            headers=checkin_headers,
        )
        assert second_response.status_code == 200
        second_data = second_response.json()
        assert second_data["summary"]["hosts_created"] == 0
        assert second_data["summary"]["arp_entries_created"] == 0
        assert second_data["summary"]["connections_created"] == 0

        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        assert (await db.execute(select(func.count(Host.id)))).scalar_one() == 3
        assert (await db.execute(select(func.count(ARPEntry.id)))).scalar_one() == 1
        assert (await db.execute(select(func.count(Connection.id)))).scalar_one() == 1
        assert (await db.execute(select(func.count(RawImport.id)))).scalar_one() == 2
        assert (await db.execute(select(func.count(AgentCheckIn.id)))).scalar_one() == 2

        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one()
        assert agent.last_seen_at is not None
        assert agent.api_key_hash is not None
        assert agent.last_ip_addresses == ["10.0.0.1", "10.0.0.10", "10.0.0.5"]

    @pytest.mark.asyncio
    async def test_rotate_agent_api_key_invalidates_previous_key(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        admin_headers = await auth_headers("admin", "agent_rotate_admin")

        policy_response = await async_client.post(
            "/api/agents/policies",
            json={
                "name": "agent-rotate-policy",
                "description": "Policy for API key rotation tests",
                "checkin_interval_seconds": 1800,
                "jitter_seconds": 60,
                "command_timeout_seconds": 15,
                "enabled_commands": {
                    "ip_neigh": True,
                    "ss_tunap": True,
                    "ip_addr": True,
                    "ip_route": True,
                },
                "max_report_bytes": 262144,
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert policy_response.status_code == 201
        policy_id = policy_response.json()["id"]

        enrollment_response = await async_client.post(
            "/api/agents/enrollment-keys",
            json={
                "name": "agent-rotate-enrollment",
                "description": "Auto-approved key for rotation tests",
                "default_policy_id": policy_id,
                "auto_approve": True,
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert enrollment_response.status_code == 201
        enrollment_key = enrollment_response.json()["enrollment_key"]

        register_response = await async_client.post(
            "/api/agents/register",
            json={
                "enrollment_key": enrollment_key,
                "agent_uuid": "agent-rotate-001",
                "display_name": "Rotate me",
                "hostname": "rotate-host-01",
                "site_name": "Lab",
                "agent_version": "0.1.0",
                "platform": "linux",
                "platform_release": "6.12",
                "addresses": [
                    {
                        "ip_address": "10.40.0.5",
                        "interface": "eth0",
                        "prefix_length": 24,
                        "mac_address": "AA:BB:CC:DD:40:05",
                    }
                ],
            },
        )
        assert register_response.status_code == 200
        register_data = register_response.json()
        agent_id = register_data["agent"]["id"]
        original_api_key = register_data["api_key"]
        assert original_api_key

        rotation_response = await async_client.post(
            f"/api/agents/{agent_id}/rotate-api-key",
            json={"reason": "lost local key file"},
            headers=admin_headers,
        )
        assert rotation_response.status_code == 200
        rotation_data = rotation_response.json()
        rotated_api_key = rotation_data["api_key"]
        assert rotated_api_key
        assert rotated_api_key != original_api_key
        assert rotation_data["agent"]["api_key_prefix"] != register_data["agent"]["api_key_prefix"]

        payload = {
            "agent_uuid": "agent-rotate-001",
            "observed_at": "2026-03-22T19:00:00Z",
            "sequence_number": 1,
            "full_snapshot": False,
            "hostname": "rotate-host-01",
            "agent_version": "0.1.0",
            "platform": "linux",
            "platform_release": "6.12",
            "addresses": [
                {
                    "ip_address": "10.40.0.5",
                    "interface": "eth0",
                    "prefix_length": 24,
                    "mac_address": "AA:BB:CC:DD:40:05",
                }
            ],
            "neighbors": [],
            "connections": [],
            "routes": [],
        }

        old_key_response = await async_client.post(
            "/api/agents/check-in",
            content=gzip.compress(json.dumps(payload).encode("utf-8")),
            headers={
                settings.AGENT_API_KEY_HEADER: original_api_key,
                "Content-Encoding": "gzip",
                "Content-Type": "application/json",
            },
        )
        assert old_key_response.status_code == 401

        new_key_response = await async_client.post(
            "/api/agents/check-in",
            content=gzip.compress(json.dumps(payload).encode("utf-8")),
            headers={
                settings.AGENT_API_KEY_HEADER: rotated_api_key,
                "Content-Encoding": "gzip",
                "Content-Type": "application/json",
            },
        )
        assert new_key_response.status_code == 200
        assert new_key_response.json()["status"] == "accepted"

        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one()
        assert agent.api_key_hash is not None
        assert agent.api_key_prefix == rotation_data["agent"]["api_key_prefix"]

    @pytest.mark.asyncio
    async def test_agent_management_reads_are_admin_only(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        admin_headers = await auth_headers("admin", "agent_read_admin")
        viewer_headers = await auth_headers("viewer", "agent_read_viewer")
        policy_id = await _create_policy(async_client, admin_headers, "read-admin-only")
        enrollment_key = await _create_enrollment_key(
            async_client,
            admin_headers,
            "read-admin-only",
            policy_id,
            auto_approve=True,
        )
        register_response = await _register_agent(
            async_client,
            enrollment_key,
            "agent-read-admin-only",
        )
        assert register_response.status_code == 200
        agent_id = register_response.json()["agent"]["id"]

        for method, path in [
            ("GET", "/api/agents/policies"),
            ("GET", "/api/agents"),
            ("GET", f"/api/agents/{agent_id}"),
            ("GET", f"/api/agents/{agent_id}/checkins"),
        ]:
            response = await async_client.request(method, path, headers=viewer_headers)
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_generic_patch_rejects_lifecycle_state_mutation(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        admin_headers = await auth_headers("admin", "agent_patch_admin")
        policy_id = await _create_policy(async_client, admin_headers, "patch-policy")
        enrollment_key = await _create_enrollment_key(
            async_client,
            admin_headers,
            "patch-enrollment",
            policy_id,
            auto_approve=False,
        )
        register_response = await _register_agent(
            async_client,
            enrollment_key,
            "agent-patch-lifecycle",
        )
        assert register_response.status_code == 200
        agent_id = register_response.json()["agent"]["id"]

        response = await async_client.patch(
            f"/api/agents/{agent_id}",
            json={
                "display_name": "Changed safely",
                "enrollment_state": "active",
                "approval_required": False,
                "is_active": False,
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

        get_response = await async_client.get(
            f"/api/agents/{agent_id}",
            headers=admin_headers,
        )
        assert get_response.status_code == 200
        assert get_response.json()["enrollment_state"] == "pending"
        assert get_response.json()["approval_required"] is True
        assert get_response.json()["is_active"] is True

    @pytest.mark.asyncio
    async def test_revoke_invalidates_key_and_reactivate_requires_approval(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        admin_headers = await auth_headers("admin", "agent_revoke_admin")
        policy_id = await _create_policy(async_client, admin_headers, "revoke-policy")
        enrollment_key = await _create_enrollment_key(
            async_client,
            admin_headers,
            "revoke-enrollment",
            policy_id,
            auto_approve=True,
        )
        register_response = await _register_agent(
            async_client,
            enrollment_key,
            "agent-revoke-001",
        )
        assert register_response.status_code == 200
        agent_id = register_response.json()["agent"]["id"]
        original_api_key = register_response.json()["api_key"]
        assert original_api_key

        first_checkin = await _post_checkin(
            async_client,
            original_api_key,
            _checkin_payload("agent-revoke-001"),
        )
        assert first_checkin.status_code == 200

        revoke_response = await async_client.post(
            f"/api/agents/{agent_id}/revoke",
            json={"reason": "decommissioned"},
            headers=admin_headers,
        )
        assert revoke_response.status_code == 200
        revoked = revoke_response.json()
        assert revoked["enrollment_state"] == "revoked"
        assert revoked["is_active"] is False
        assert revoked["api_key_prefix"] is None

        old_key_response = await _post_checkin(
            async_client,
            original_api_key,
            _checkin_payload("agent-revoke-001", observed_at="2026-03-22T20:10:00Z"),
        )
        assert old_key_response.status_code == 401

        rotate_response = await async_client.post(
            f"/api/agents/{agent_id}/rotate-api-key",
            json={"reason": "should fail"},
            headers=admin_headers,
        )
        assert rotate_response.status_code == 409

        reactivate_response = await async_client.post(
            f"/api/agents/{agent_id}/reactivate",
            json={"reason": "returning to service"},
            headers=admin_headers,
        )
        assert reactivate_response.status_code == 200
        reactivated = reactivate_response.json()
        assert reactivated["enrollment_state"] == "pending"
        assert reactivated["approval_required"] is True
        assert reactivated["is_active"] is True
        assert reactivated["api_key_prefix"] is None

        approve_response = await async_client.post(
            f"/api/agents/{agent_id}/approve",
            json={"policy_id": policy_id},
            headers=admin_headers,
        )
        assert approve_response.status_code == 200
        assert approve_response.json()["enrollment_state"] == "active"

        poll_response = await _register_agent(
            async_client,
            enrollment_key,
            "agent-revoke-001",
        )
        assert poll_response.status_code == 200
        new_api_key = poll_response.json()["api_key"]
        assert new_api_key
        assert new_api_key != original_api_key

        old_key_after_reactivate = await _post_checkin(
            async_client,
            original_api_key,
            _checkin_payload("agent-revoke-001", observed_at="2026-03-22T20:20:00Z"),
        )
        assert old_key_after_reactivate.status_code == 401

        new_key_response = await _post_checkin(
            async_client,
            new_api_key,
            _checkin_payload("agent-revoke-001", observed_at="2026-03-22T20:30:00Z"),
        )
        assert new_key_response.status_code == 200

    @pytest.mark.asyncio
    async def test_enrollment_key_negative_cases(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        admin_headers = await auth_headers("admin", "agent_key_admin")
        policy_id = await _create_policy(async_client, admin_headers, "key-negative-policy")

        inactive_key = await _create_enrollment_key(
            async_client,
            admin_headers,
            "inactive-key",
            policy_id,
            is_active=False,
        )
        inactive_response = await _register_agent(
            async_client,
            inactive_key,
            "agent-inactive-key",
        )
        assert inactive_response.status_code == 401

        expired_at = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
            tzinfo=None,
            microsecond=0,
        ).isoformat()
        expired_key = await _create_enrollment_key(
            async_client,
            admin_headers,
            "expired-key",
            policy_id,
            expires_at=expired_at,
        )
        expired_response = await _register_agent(
            async_client,
            expired_key,
            "agent-expired-key",
        )
        assert expired_response.status_code == 403

        limited_key = await _create_enrollment_key(
            async_client,
            admin_headers,
            "limited-key",
            policy_id,
            max_registrations=1,
        )
        first_response = await _register_agent(
            async_client,
            limited_key,
            "agent-limited-001",
        )
        assert first_response.status_code == 200

        second_response = await _register_agent(
            async_client,
            limited_key,
            "agent-limited-002",
            ip_address="10.70.0.6",
            mac_address="AA:BB:CC:70:00:06",
        )
        assert second_response.status_code == 403

    @pytest.mark.asyncio
    async def test_checkin_auth_and_payload_negative_cases(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        admin_headers = await auth_headers("admin", "agent_checkin_negative_admin")
        policy_id = await _create_policy(async_client, admin_headers, "checkin-negative-policy")
        enrollment_key = await _create_enrollment_key(
            async_client,
            admin_headers,
            "checkin-negative-enrollment",
            policy_id,
        )
        register_response = await _register_agent(
            async_client,
            enrollment_key,
            "agent-checkin-negative",
        )
        assert register_response.status_code == 200
        api_key = register_response.json()["api_key"]
        payload = _checkin_payload("agent-checkin-negative")

        missing_key_response = await async_client.post(
            "/api/agents/check-in",
            content=gzip.compress(json.dumps(payload).encode("utf-8")),
            headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
        )
        assert missing_key_response.status_code == 401

        invalid_key_response = await _post_checkin(
            async_client,
            "gpak_not-a-real-key",
            payload,
        )
        assert invalid_key_response.status_code == 401

        mismatch_payload = dict(payload)
        mismatch_payload["agent_uuid"] = "different-agent"
        mismatch_response = await _post_checkin(
            async_client,
            api_key,
            mismatch_payload,
        )
        assert mismatch_response.status_code == 409

        unsupported_encoding_response = await async_client.post(
            "/api/agents/check-in",
            content=json.dumps(payload).encode("utf-8"),
            headers={
                settings.AGENT_API_KEY_HEADER: api_key,
                "Content-Encoding": "br",
                "Content-Type": "application/json",
            },
        )
        assert unsupported_encoding_response.status_code == 415

        invalid_gzip_response = await async_client.post(
            "/api/agents/check-in",
            content=b"not gzip",
            headers={
                settings.AGENT_API_KEY_HEADER: api_key,
                "Content-Encoding": "gzip",
                "Content-Type": "application/json",
            },
        )
        assert invalid_gzip_response.status_code == 400

        compressed_too_large_response = await async_client.post(
            "/api/agents/check-in",
            content=b"x" * (settings.AGENT_MAX_REPORT_BYTES + 1),
            headers={
                settings.AGENT_API_KEY_HEADER: api_key,
                "Content-Type": "application/json",
            },
        )
        assert compressed_too_large_response.status_code == 413

        decoded_too_large_payload = dict(payload)
        decoded_too_large_payload["metadata"] = {
            "blob": "x" * (settings.AGENT_MAX_REPORT_BYTES + 1)
        }
        decoded_too_large_response = await async_client.post(
            "/api/agents/check-in",
            content=gzip.compress(json.dumps(decoded_too_large_payload).encode("utf-8")),
            headers={
                settings.AGENT_API_KEY_HEADER: api_key,
                "Content-Encoding": "gzip",
                "Content-Type": "application/json",
            },
        )
        assert decoded_too_large_response.status_code == 413
