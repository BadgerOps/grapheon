import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent.grapheon_agent import (
    AgentConfig,
    build_delta,
    parse_ip_addr_json,
    parse_ip_neigh_json,
    parse_netstat_output,
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


def test_build_delta_returns_full_snapshot_first_then_incremental():
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

    full_delta, full_snapshot = build_delta(current, {})
    incremental_delta, incremental_snapshot = build_delta(current, previous)

    assert full_snapshot is True
    assert full_delta == current
    assert incremental_snapshot is False
    assert incremental_delta["addresses"] == []
    assert incremental_delta["neighbors"] == [{"ip_address": "10.20.0.1"}]


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
    assert "Examples:" in result.stdout
    assert "python3 agent/grapheon_agent.py" in result.stdout


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
    )

    with pytest.raises(RuntimeError, match="existing local agent API key"):
        run_agent(config, force=False, check_in_only=True)
