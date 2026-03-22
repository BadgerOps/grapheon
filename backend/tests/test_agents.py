import gzip
import json

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
