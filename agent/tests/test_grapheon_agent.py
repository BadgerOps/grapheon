import subprocess
import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent.grapheon_agent import (
    AgentConfig,
    DEFAULT_USER_AGENT,
    build_snapshot_payload,
    build_config,
    http_json,
    parse_ip_addr_json,
    parse_ip_neigh_json,
    parse_netstat_output,
    parse_args,
    parse_ss_output,
    parse_timestamp,
    run_agent,
    should_run_with_policy,
)


def test_parse_ip_addr_json_ignores_loopback_and_extracts_mac():
    payload = """
    [
      {
        "ifname": "lo",
        "address": "00:00:00:00:00:00",
        "addr_info": [{"local": "127.0.0.1", "prefixlen": 8}]
      },
      {
        "ifname": "eth0",
        "address": "aa:bb:cc:dd:ee:ff",
        "addr_info": [
          {"local": "10.20.0.5", "prefixlen": 24},
          {"local": "fe80::1", "prefixlen": 64}
        ]
      }
    ]
    """

    result = parse_ip_addr_json(payload)

    assert result == [
        {
            "interface": "eth0",
            "ip_address": "10.20.0.5",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "prefix_length": 24,
        },
        {
            "interface": "eth0",
            "ip_address": "fe80::1",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "prefix_length": 64,
        },
    ]


def test_parse_ip_neigh_json_handles_state_arrays():
    payload = """
    [
      {"dst": "10.20.0.1", "lladdr": "11:22:33:44:55:66", "dev": "eth0", "state": ["REACHABLE"]},
      {"dst": "fe80::2", "lladdr": "22:33:44:55:66:77", "dev": "eth0", "state": "STALE"}
    ]
    """

    result = parse_ip_neigh_json(payload)

    assert result == [
        {
            "interface": "eth0",
            "ip_address": "10.20.0.1",
            "mac_address": "11:22:33:44:55:66",
            "state": "reachable",
        },
        {
            "interface": "eth0",
            "ip_address": "fe80::2",
            "mac_address": "22:33:44:55:66:77",
            "state": "stale",
        },
    ]


def test_parse_ss_output_extracts_pid_and_process_name():
    output = (
        'tcp ESTAB 0 0 10.20.0.5:443 10.20.0.10:51514 '
        'users:(("python",pid=777,fd=5))\n'
        'udp UNCONN 0 0 0.0.0.0:68 0.0.0.0:* '
        'users:(("dhclient",pid=101,fd=7))'
    )

    result = parse_ss_output(output)

    assert result == [
        {
            "local_ip": "0.0.0.0",
            "local_port": 68,
            "pid": 101,
            "process_name": "dhclient",
            "protocol": "udp",
            "remote_ip": "0.0.0.0",
            "remote_port": None,
            "state": "unknown",
        },
        {
            "local_ip": "10.20.0.5",
            "local_port": 443,
            "pid": 777,
            "process_name": "python",
            "protocol": "tcp",
            "remote_ip": "10.20.0.10",
            "remote_port": 51514,
            "state": "established",
        },
    ]


def test_parse_netstat_output_supports_udp_without_state():
    output = (
        "tcp        0      0 10.20.0.5:22       10.20.0.10:51514   ESTABLISHED 100/sshd\n"
        "udp        0      0 0.0.0.0:68         0.0.0.0:*                     101/dhclient"
    )

    result = parse_netstat_output(output)

    assert result == [
        {
            "local_ip": "0.0.0.0",
            "local_port": 68,
            "pid": 101,
            "process_name": "dhclient",
            "protocol": "udp",
            "remote_ip": "0.0.0.0",
            "remote_port": None,
            "state": "unknown",
        },
        {
            "local_ip": "10.20.0.5",
            "local_port": 22,
            "pid": 100,
            "process_name": "sshd",
            "protocol": "tcp",
            "remote_ip": "10.20.0.10",
            "remote_port": 51514,
            "state": "established",
        },
    ]


def test_build_snapshot_payload_returns_full_snapshot_every_time():
    current = {
        "addresses": [{"ip_address": "10.20.0.5"}],
        "neighbors": [{"ip_address": "10.20.0.1"}],
        "connections": [],
        "routes": [],
    }
    previous = {
        "addresses": [{"ip_address": "10.20.0.5"}],
        "neighbors": [],
        "connections": [],
        "routes": [],
    }

    first_payload, first_snapshot = build_snapshot_payload(current, {})
    repeated_payload, repeated_snapshot = build_snapshot_payload(current, previous)

    assert first_snapshot is True
    assert first_payload == current
    assert repeated_snapshot is True
    assert repeated_payload == current


def test_should_run_with_policy_respects_interval():
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    stale = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")

    policy = {"checkin_interval_seconds": 3600}

    assert should_run_with_policy({}, policy, timer_interval_seconds=900, force=False) is True
    assert (
        should_run_with_policy(
            {"last_successful_checkin_at": recent},
            policy,
            timer_interval_seconds=900,
            force=False,
        )
        is False
    )
    assert (
        should_run_with_policy(
            {"last_successful_checkin_at": stale},
            policy,
            timer_interval_seconds=900,
            force=False,
        )
        is True
    )
    assert (
        should_run_with_policy(
            {"last_successful_checkin_at": recent},
            policy,
            timer_interval_seconds=900,
            force=True,
        )
        is True
    )


def test_parse_timestamp_accepts_naive_and_utc_z():
    assert parse_timestamp("2026-03-22T18:00:00Z") is not None
    naive = parse_timestamp("2026-03-22T18:00:00")
    assert naive is not None
    assert naive.tzinfo == timezone.utc


def test_help_output_mentions_manual_modes_and_examples():
    script = Path(__file__).resolve().parents[1] / "grapheon_agent.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--register-only" in result.stdout
    assert "--check-in-only" in result.stdout
    assert "--user-agent" in result.stdout
    assert "Examples:" in result.stdout
    assert "python3 agent/grapheon_agent.py" in result.stdout
    assert "/opt/grapheon/agent/current/grapheon_agent.py" in result.stdout


def test_build_config_uses_default_user_agent(monkeypatch, tmp_path):
    monkeypatch.delenv("GRAPHEON_AGENT_SERVER_URL", raising=False)
    monkeypatch.delenv("GRAPHEON_AGENT_USER_AGENT", raising=False)
    args = parse_args(
        [
            "--server-url",
            "https://grapheon.example.com",
            "--state-dir",
            str(tmp_path),
            "--config",
            str(tmp_path / "missing.env"),
        ]
    )

    config = build_config(args)

    assert config.user_agent == DEFAULT_USER_AGENT


def test_build_config_reads_user_agent_from_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GRAPHEON_AGENT_SERVER_URL", raising=False)
    monkeypatch.delenv("GRAPHEON_AGENT_USER_AGENT", raising=False)
    env_file = tmp_path / "agent.env"
    env_file.write_text(
        "\n".join(
            [
                "GRAPHEON_AGENT_SERVER_URL=https://grapheon.example.com",
                "GRAPHEON_AGENT_USER_AGENT=Custom-Agent/1.0",
            ]
        )
    )
    args = parse_args(["--config", str(env_file), "--state-dir", str(tmp_path)])

    config = build_config(args)

    assert config.user_agent == "Custom-Agent/1.0"


def test_build_config_cli_user_agent_overrides_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GRAPHEON_AGENT_SERVER_URL", raising=False)
    monkeypatch.delenv("GRAPHEON_AGENT_USER_AGENT", raising=False)
    env_file = tmp_path / "agent.env"
    env_file.write_text(
        "\n".join(
            [
                "GRAPHEON_AGENT_SERVER_URL=https://grapheon.example.com",
                "GRAPHEON_AGENT_USER_AGENT=Env-Agent/1.0",
            ]
        )
    )
    args = parse_args(
        [
            "--config",
            str(env_file),
            "--state-dir",
            str(tmp_path),
            "--user-agent",
            "Cli-Agent/2.0",
        ]
    )

    config = build_config(args)

    assert config.user_agent == "Cli-Agent/2.0"


def test_http_json_sends_configured_user_agent(monkeypatch, tmp_path):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout, context):
        captured["request"] = req
        captured["timeout"] = timeout
        captured["context"] = context
        return FakeResponse()

    monkeypatch.setattr("agent.grapheon_agent.request.urlopen", fake_urlopen)
    config = AgentConfig(
        server_url="https://grapheon.example.com",
        enrollment_key=None,
        state_dir=tmp_path,
        config_path=tmp_path / "agent.env",
        request_timeout_seconds=30,
        verify_tls=True,
        ca_file=None,
        display_name=None,
        site_name=None,
        hostname=None,
        timer_interval_seconds=900,
        api_key_header="X-Agent-Api-Key",
        user_agent="Custom-Agent/1.0",
    )

    http_json(
        config,
        "POST",
        "api/agents/check-in",
        {"agent_uuid": "agent-1"},
        headers={"X-Agent-Api-Key": "secret"},
        compress=True,
    )

    headers = {key.lower(): value for key, value in captured["request"].header_items()}
    assert headers["user-agent"] == "Custom-Agent/1.0"
    assert headers["x-agent-api-key"] == "secret"
    assert headers["content-encoding"] == "gzip"


def test_run_agent_polls_before_skipping_for_cached_interval(monkeypatch, tmp_path):
    (tmp_path / "agent_uuid").write_text("agent-poll-1\n")
    (tmp_path / "api_key").write_text("secret\n")
    recent = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "last_successful_checkin_at": recent,
                "policy": {"checkin_interval_seconds": 3600},
            }
        )
    )
    calls = []

    def fake_poll(config, api_key, agent_uuid_value):
        calls.append((api_key, agent_uuid_value))
        return {
            "policy": {"checkin_interval_seconds": 3600},
            "collection_request": {"requested": False},
        }

    monkeypatch.setattr("agent.grapheon_agent.poll_agent_control", fake_poll)
    monkeypatch.setattr(
        "agent.grapheon_agent.build_current_snapshot",
        lambda policy: pytest.fail("collection should not run"),
    )
    config = AgentConfig(
        server_url="https://grapheon.example.com",
        enrollment_key=None,
        state_dir=tmp_path,
        config_path=tmp_path / "agent.env",
        request_timeout_seconds=30,
        verify_tls=True,
        ca_file=None,
        display_name=None,
        site_name=None,
        hostname=None,
        timer_interval_seconds=900,
        api_key_header="X-Agent-Api-Key",
        user_agent=DEFAULT_USER_AGENT,
    )

    assert run_agent(config, force=False) == 0
    assert calls == [("secret", "agent-poll-1")]


def test_run_agent_on_demand_request_bypasses_cached_interval(monkeypatch, tmp_path):
    (tmp_path / "agent_uuid").write_text("agent-poll-2\n")
    (tmp_path / "api_key").write_text("secret\n")
    recent = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "last_successful_checkin_at": recent,
                "policy": {"checkin_interval_seconds": 3600, "jitter_seconds": 0},
            }
        )
    )
    checkins = []

    def fake_poll(config, api_key, agent_uuid_value):
        return {
            "policy": {"checkin_interval_seconds": 3600, "jitter_seconds": 0},
            "collection_request": {
                "requested": True,
                "requested_at": "2026-06-11T12:00:00Z",
            },
        }

    def fake_check_in(config, api_key, payload):
        checkins.append(payload)
        return {
            "server_time": "2026-06-11T12:01:00Z",
            "summary": {"accepted": True},
            "policy": {"checkin_interval_seconds": 3600, "jitter_seconds": 0},
        }

    monkeypatch.setattr("agent.grapheon_agent.poll_agent_control", fake_poll)
    monkeypatch.setattr("agent.grapheon_agent.maybe_sleep_for_policy_jitter", lambda policy: 0)
    monkeypatch.setattr(
        "agent.grapheon_agent.build_current_snapshot",
        lambda policy: {
            "addresses": [],
            "neighbors": [],
            "connections": [],
            "routes": [],
        },
    )
    monkeypatch.setattr("agent.grapheon_agent.check_in_agent", fake_check_in)
    config = AgentConfig(
        server_url="https://grapheon.example.com",
        enrollment_key=None,
        state_dir=tmp_path,
        config_path=tmp_path / "agent.env",
        request_timeout_seconds=30,
        verify_tls=True,
        ca_file=None,
        display_name=None,
        site_name=None,
        hostname=None,
        timer_interval_seconds=900,
        api_key_header="X-Agent-Api-Key",
        user_agent=DEFAULT_USER_AGENT,
    )

    assert run_agent(config, force=False) == 0
    assert len(checkins) == 1
    assert checkins[0]["agent_uuid"] == "agent-poll-2"
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["last_collection_request_at"] == "2026-06-11T12:00:00Z"


def test_check_in_only_requires_existing_api_key(tmp_path):
    config = AgentConfig(
        server_url="https://grapheon.example.com",
        enrollment_key=None,
        state_dir=tmp_path,
        config_path=tmp_path / "agent.env",
        request_timeout_seconds=30,
        verify_tls=True,
        ca_file=None,
        display_name=None,
        site_name=None,
        hostname=None,
        timer_interval_seconds=900,
        api_key_header="X-Agent-Api-Key",
        user_agent=DEFAULT_USER_AGENT,
    )

    with pytest.raises(RuntimeError, match="existing local agent API key"):
        run_agent(config, force=False, check_in_only=True)
