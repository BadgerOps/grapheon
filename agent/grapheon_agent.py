#!/usr/bin/env python3
"""Low-impact one-shot passive collector for Graphēon."""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import platform
import random
import shutil
import socket
import ssl
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib import error, request


DEFAULT_POLICY = {
    "checkin_interval_seconds": 3600,
    "jitter_seconds": 300,
    "command_timeout_seconds": 15,
    "enabled_commands": {
        "ip_neigh": True,
        "ss_tunap": True,
        "ip_addr": True,
        "ip_route": True,
    },
}

DEFAULT_STATE_DIR = "/var/lib/grapheon-agent"
DEFAULT_CONFIG_PATH = "/etc/grapheon-agent.env"
DEFAULT_TIMER_INTERVAL_SECONDS = 900
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_API_KEY_HEADER = "X-Agent-Api-Key"
STATE_FILENAME = "state.json"
AGENT_UUID_FILENAME = "agent_uuid"
API_KEY_FILENAME = "api_key"

LOG = logging.getLogger("grapheon_agent")

CLI_DESCRIPTION = (
    "Low-impact one-shot passive collector for Graphēon.\n\n"
    "The agent can run from a systemd timer or be invoked directly with flags "
    "for manual registration, approval polling, and check-in."
)

CLI_EPILOG = """Examples:
  Register or poll approval directly from a repo checkout:
    python3 agent/grapheon_agent.py --server-url https://grapheon.example.com --enrollment-key gaek_xxx --state-dir ./agent-state --register-only

  Force an immediate manual check-in using an existing local state dir:
    python3 agent/grapheon_agent.py --server-url https://grapheon.example.com --state-dir ./agent-state --force --log-level DEBUG

  Run the installed host copy without systemd:
    /usr/bin/env python3 /opt/grapheon/agent/grapheon_agent.py --config /etc/grapheon-agent.env --force
"""


def _load_agent_version() -> str:
    version_path = Path(__file__).with_name("VERSION")
    try:
        return version_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0-dev"


AGENT_VERSION = _load_agent_version()


@dataclass
class AgentConfig:
    server_url: str
    enrollment_key: Optional[str]
    state_dir: Path
    config_path: Path
    request_timeout_seconds: int
    verify_tls: bool
    ca_file: Optional[str]
    display_name: Optional[str]
    site_name: Optional[str]
    hostname: Optional[str]
    timer_interval_seconds: int
    api_key_header: str


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=CLI_DESCRIPTION,
        epilog=CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("GRAPHEON_AGENT_CONFIG", DEFAULT_CONFIG_PATH),
        help="Path to an optional KEY=VALUE environment file",
    )
    parser.add_argument(
        "--state-dir",
        default=os.environ.get("GRAPHEON_AGENT_STATE_DIR", DEFAULT_STATE_DIR),
        help="Directory for agent_uuid, api_key, and runtime state",
    )
    parser.add_argument(
        "--server-url",
        default=os.environ.get("GRAPHEON_AGENT_SERVER_URL"),
        help="Base Graphēon server URL, for example https://grapheon.example.com",
    )
    parser.add_argument(
        "--enrollment-key",
        default=os.environ.get("GRAPHEON_AGENT_ENROLLMENT_KEY"),
        help="Bootstrap enrollment key used until an API key is issued",
    )
    parser.add_argument(
        "--display-name",
        default=os.environ.get("GRAPHEON_AGENT_DISPLAY_NAME"),
        help="Optional display name shown in the Graphēon registry",
    )
    parser.add_argument(
        "--site-name",
        default=os.environ.get("GRAPHEON_AGENT_SITE_NAME"),
        help="Optional site name shown in the Graphēon registry",
    )
    parser.add_argument(
        "--hostname",
        default=os.environ.get("GRAPHEON_AGENT_HOSTNAME"),
        help="Override detected hostname",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=int,
        default=int(
            os.environ.get(
                "GRAPHEON_AGENT_REQUEST_TIMEOUT_SECONDS",
                str(DEFAULT_REQUEST_TIMEOUT_SECONDS),
            )
        ),
        help="HTTP request timeout in seconds",
    )
    parser.add_argument(
        "--timer-interval-seconds",
        type=int,
        default=int(
            os.environ.get(
                "GRAPHEON_AGENT_TIMER_INTERVAL_SECONDS",
                str(DEFAULT_TIMER_INTERVAL_SECONDS),
            )
        ),
        help="Local timer interval used for cadence gating in seconds",
    )
    parser.add_argument(
        "--api-key-header",
        default=os.environ.get("GRAPHEON_AGENT_API_KEY_HEADER", DEFAULT_API_KEY_HEADER),
        help="HTTP header used to send the per-agent API key",
    )
    parser.add_argument(
        "--ca-file",
        default=os.environ.get("GRAPHEON_AGENT_CA_FILE"),
        help="Optional CA bundle path for HTTPS validation",
    )
    parser.add_argument(
        "--insecure-skip-verify",
        action="store_true",
        default=_env_bool("GRAPHEON_AGENT_INSECURE_SKIP_VERIFY", False),
        help="Disable TLS certificate validation for development only",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--register-only",
        action="store_true",
        help="Register or poll approval, store any issued API key, and exit without collecting",
    )
    mode_group.add_argument(
        "--check-in-only",
        action="store_true",
        help="Collect and check in using an existing local API key without registration",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass cached policy cadence gating for this run",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("GRAPHEON_AGENT_LOG_LEVEL", "INFO"),
        help="Logging level such as DEBUG, INFO, WARNING, or ERROR",
    )
    return parser.parse_args(argv)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def build_config(args: argparse.Namespace) -> AgentConfig:
    config_path = Path(args.config)
    load_env_file(config_path)

    server_url = args.server_url or os.environ.get("GRAPHEON_AGENT_SERVER_URL")
    enrollment_key = args.enrollment_key or os.environ.get("GRAPHEON_AGENT_ENROLLMENT_KEY")
    display_name = args.display_name or os.environ.get("GRAPHEON_AGENT_DISPLAY_NAME")
    site_name = args.site_name or os.environ.get("GRAPHEON_AGENT_SITE_NAME")
    hostname = args.hostname or os.environ.get("GRAPHEON_AGENT_HOSTNAME")
    ca_file = args.ca_file or os.environ.get("GRAPHEON_AGENT_CA_FILE")

    if not server_url:
        raise SystemExit("GRAPHEON_AGENT_SERVER_URL is required")

    return AgentConfig(
        server_url=server_url.rstrip("/"),
        enrollment_key=enrollment_key,
        state_dir=Path(args.state_dir),
        config_path=config_path,
        request_timeout_seconds=args.request_timeout_seconds,
        verify_tls=not args.insecure_skip_verify,
        ca_file=ca_file,
        display_name=display_name,
        site_name=site_name,
        hostname=hostname,
        timer_interval_seconds=args.timer_interval_seconds,
        api_key_header=args.api_key_header,
    )


def state_file_path(config: AgentConfig) -> Path:
    return config.state_dir / STATE_FILENAME


def agent_uuid_path(config: AgentConfig) -> Path:
    return config.state_dir / AGENT_UUID_FILENAME


def api_key_path(config: AgentConfig) -> Path:
    return config.state_dir / API_KEY_FILENAME


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> Optional[datetime]:
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def ensure_state_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json_file(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default.copy()
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        LOG.warning("State file %s is invalid; starting fresh", path)
        return default.copy()


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    temp_path.replace(path)
    path.chmod(0o600)


def read_text_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return path.read_text().strip() or None


def write_text_file(path: Path, value: str) -> None:
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(f"{value}\n")
    temp_path.replace(path)
    path.chmod(0o600)


def ensure_agent_uuid(config: AgentConfig) -> str:
    path = agent_uuid_path(config)
    existing = read_text_file(path)
    if existing:
        return existing
    agent_uuid = str(uuid.uuid4())
    write_text_file(path, agent_uuid)
    return agent_uuid


def build_ssl_context(config: AgentConfig):
    if not config.server_url.startswith("https://"):
        return None
    if not config.verify_tls:
        return ssl._create_unverified_context()
    context = ssl.create_default_context(cafile=config.ca_file)
    return context


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def canonicalize_entries(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [json.loads(canonical_json(entry)) for entry in entries]
    normalized.sort(key=canonical_json)
    return normalized


def build_delta(current: dict[str, list[dict[str, Any]]], previous: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, list[dict[str, Any]]], bool]:
    if not previous:
        return current, True

    delta: dict[str, list[dict[str, Any]]] = {}
    for key, current_entries in current.items():
        previous_set = {canonical_json(entry) for entry in previous.get(key, [])}
        delta[key] = [
            entry
            for entry in current_entries
            if canonical_json(entry) not in previous_set
        ]
    return delta, False


def normalize_ip(value: str) -> Optional[str]:
    raw = value.strip()
    if not raw:
        return None
    if raw == "*":
        return "0.0.0.0"
    if raw.startswith("[") and "]" in raw:
        raw = raw[1 : raw.index("]")]
    raw = raw.split("%", 1)[0]
    try:
        parsed = ip_address(raw)
    except ValueError:
        return None
    if parsed.is_unspecified:
        return "0.0.0.0" if parsed.version == 4 else "::"
    return str(parsed)


def split_host_port(endpoint: str) -> tuple[Optional[str], Optional[int]]:
    raw = endpoint.strip()
    if not raw or raw == "*":
        return "0.0.0.0", None
    if raw.endswith(":*"):
        host = raw[:-2]
        return normalize_ip(host) or "0.0.0.0", None
    if raw.startswith("[") and "]" in raw:
        host, _, remainder = raw[1:].partition("]")
        port = remainder[1:] if remainder.startswith(":") else None
        return normalize_ip(host), int(port) if port and port.isdigit() else None
    if raw.count(":") > 1 and raw.rsplit(":", 1)[1].isdigit():
        host, port = raw.rsplit(":", 1)
        return normalize_ip(host), int(port)
    if raw.count(":") == 1 and raw.rsplit(":", 1)[1].isdigit():
        host, port = raw.rsplit(":", 1)
        return normalize_ip(host), int(port)
    host = normalize_ip(raw)
    return host, None


def normalize_state(protocol: str, state_value: Optional[str]) -> str:
    if not state_value:
        return "unknown"
    normalized = state_value.strip().lower().replace("-", "_")
    aliases = {
        "estab": "established",
        "listen": "listen",
        "unconn": "unknown",
        "connected": "established",
        "syn_recv": "syn_recv",
        "syn_sent": "syn_sent",
        "time_wait": "time_wait",
        "close_wait": "close_wait",
        "fin_wait_1": "fin_wait1",
        "fin_wait_2": "fin_wait2",
        "last_ack": "last_ack",
    }
    normalized = aliases.get(normalized, normalized)
    if protocol == "udp" and normalized == "unknown":
        return "unknown"
    return normalized


def parse_process_field(value: str) -> tuple[Optional[int], Optional[str]]:
    if not value:
        return None, None
    name = None
    pid = None
    marker = "(("
    if marker in value:
        after = value.split(marker, 1)[1]
        if '"' in after:
            parts = after.split('"')
            if len(parts) > 1:
                name = parts[1]
        if "pid=" in after:
            try:
                pid = int(after.split("pid=", 1)[1].split(",", 1)[0].split(")", 1)[0])
            except ValueError:
                pid = None
    return pid, name


def parse_ip_addr_json(output: str) -> list[dict[str, Any]]:
    records = []
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return records
    for iface in payload:
        if iface.get("ifname") == "lo":
            continue
        mac_address = iface.get("address")
        for addr_info in iface.get("addr_info", []):
            local = normalize_ip(addr_info.get("local", ""))
            if not local:
                continue
            records.append(
                {
                    "ip_address": local,
                    "interface": iface.get("ifname"),
                    "prefix_length": addr_info.get("prefixlen"),
                    "mac_address": mac_address,
                }
            )
    return canonicalize_entries(records)


def parse_ip_route_json(output: str) -> list[dict[str, Any]]:
    records = []
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return records
    for route in payload:
        gateway = normalize_ip(str(route.get("gateway", ""))) if route.get("gateway") else None
        source_ip = normalize_ip(str(route.get("prefsrc", ""))) if route.get("prefsrc") else None
        destination = route.get("dst") or "default"
        records.append(
            {
                "destination": destination,
                "gateway": gateway,
                "interface": route.get("dev"),
                "source_ip": source_ip,
            }
        )
    return canonicalize_entries(records)


def parse_ip_neigh_json(output: str) -> list[dict[str, Any]]:
    records = []
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return records
    for entry in payload:
        ip_addr = normalize_ip(str(entry.get("dst", "")))
        if not ip_addr:
            continue
        state_value = entry.get("state")
        if isinstance(state_value, list):
            state_value = ",".join(state_value)
        records.append(
            {
                "ip_address": ip_addr,
                "mac_address": entry.get("lladdr"),
                "interface": entry.get("dev"),
                "state": state_value.lower() if isinstance(state_value, str) else None,
            }
        )
    return canonicalize_entries(records)


def parse_ss_output(output: str) -> list[dict[str, Any]]:
    records = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 6)
        if len(parts) < 5:
            continue
        protocol = parts[0].lower()
        if protocol not in {"tcp", "udp"}:
            continue
        state_value = parts[1] if len(parts) > 1 else None
        local_field = parts[4] if len(parts) > 4 else ""
        remote_field = parts[5] if len(parts) > 5 else ""
        process_field = parts[6] if len(parts) > 6 else ""
        local_ip, local_port = split_host_port(local_field)
        remote_ip, remote_port = split_host_port(remote_field)
        if not local_ip or local_port is None or not remote_ip:
            continue
        pid, process_name = parse_process_field(process_field)
        records.append(
            {
                "local_ip": local_ip,
                "local_port": local_port,
                "remote_ip": remote_ip,
                "remote_port": remote_port,
                "protocol": protocol,
                "state": normalize_state(protocol, state_value),
                "pid": pid,
                "process_name": process_name,
            }
        )
    return canonicalize_entries(records)


def parse_netstat_output(output: str) -> list[dict[str, Any]]:
    records = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("proto"):
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        protocol = parts[0].lower()
        if protocol not in {"tcp", "udp"}:
            continue
        local_ip, local_port = split_host_port(parts[3])
        remote_ip, remote_port = split_host_port(parts[4])
        if not local_ip or local_port is None or not remote_ip:
            continue
        state_value = parts[5] if protocol == "tcp" and len(parts) > 5 else "unknown"
        process_index = 6 if protocol == "tcp" else 5
        process_field = parts[process_index] if len(parts) > process_index else ""
        pid = None
        process_name = None
        if "/" in process_field:
            pid_part, process_name = process_field.split("/", 1)
            try:
                pid = int(pid_part)
            except ValueError:
                pid = None
        records.append(
            {
                "local_ip": local_ip,
                "local_port": local_port,
                "remote_ip": remote_ip,
                "remote_port": remote_port,
                "protocol": protocol,
                "state": normalize_state(protocol, state_value),
                "pid": pid,
                "process_name": process_name,
            }
        )
    return canonicalize_entries(records)


def choose_command(*candidates: list[str]) -> Optional[list[str]]:
    for candidate in candidates:
        if shutil.which(candidate[0]):
            return candidate
    return None


def run_command(command: list[str], timeout_seconds: int) -> str:
    completed = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
    )
    return completed.stdout


def collect_addresses(timeout_seconds: int) -> list[dict[str, Any]]:
    command = choose_command(["ip", "-json", "addr", "show"])
    if not command:
        LOG.warning("Skipping address collection: ip command not found")
        return []
    try:
        return parse_ip_addr_json(run_command(command, timeout_seconds))
    except (subprocess.SubprocessError, OSError) as exc:
        LOG.warning("Address collection failed: %s", exc)
        return []


def collect_routes(timeout_seconds: int) -> list[dict[str, Any]]:
    command = choose_command(["ip", "-json", "route", "show"])
    if not command:
        LOG.warning("Skipping route collection: ip command not found")
        return []
    try:
        return parse_ip_route_json(run_command(command, timeout_seconds))
    except (subprocess.SubprocessError, OSError) as exc:
        LOG.warning("Route collection failed: %s", exc)
        return []


def collect_neighbors(timeout_seconds: int) -> list[dict[str, Any]]:
    command = choose_command(["ip", "-json", "neigh", "show"])
    if not command:
        LOG.warning("Skipping neighbor collection: ip command not found")
        return []
    try:
        return parse_ip_neigh_json(run_command(command, timeout_seconds))
    except (subprocess.SubprocessError, OSError) as exc:
        LOG.warning("Neighbor collection failed: %s", exc)
        return []


def collect_connections(timeout_seconds: int) -> list[dict[str, Any]]:
    command = choose_command(["ss", "-tunapH"], ["netstat", "-tunap"])
    if not command:
        LOG.warning("Skipping connection collection: ss/netstat command not found")
        return []
    try:
        output = run_command(command, timeout_seconds)
    except (subprocess.SubprocessError, OSError) as exc:
        LOG.warning("Connection collection failed: %s", exc)
        return []
    if command[0] == "netstat":
        return parse_netstat_output(output)
    return parse_ss_output(output)


def build_registration_payload(config: AgentConfig, agent_uuid_value: str) -> dict[str, Any]:
    timeout_seconds = DEFAULT_POLICY["command_timeout_seconds"]
    return {
        "enrollment_key": config.enrollment_key,
        "agent_uuid": agent_uuid_value,
        "display_name": config.display_name,
        "hostname": config.hostname or socket.gethostname(),
        "site_name": config.site_name,
        "agent_version": AGENT_VERSION,
        "platform": platform.system().lower(),
        "platform_release": platform.release(),
        "metadata": {"runtime": "python-stdlib", "timer_model": "systemd-oneshot"},
        "addresses": collect_addresses(timeout_seconds),
    }


def build_current_snapshot(policy: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    timeout_seconds = int(policy.get("command_timeout_seconds", DEFAULT_POLICY["command_timeout_seconds"]))
    commands = policy.get("enabled_commands") or DEFAULT_POLICY["enabled_commands"]
    snapshot = {
        "addresses": collect_addresses(timeout_seconds) if commands.get("ip_addr", True) else [],
        "neighbors": collect_neighbors(timeout_seconds) if commands.get("ip_neigh", True) else [],
        "connections": collect_connections(timeout_seconds) if commands.get("ss_tunap", True) else [],
        "routes": collect_routes(timeout_seconds) if commands.get("ip_route", True) else [],
    }
    return {key: canonicalize_entries(value) for key, value in snapshot.items()}


def http_json(
    config: AgentConfig,
    method: str,
    path: str,
    payload: dict[str, Any],
    headers: Optional[dict[str, str]] = None,
    compress: bool = False,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    if compress:
        body = gzip.compress(body)
        request_headers["Content-Encoding"] = "gzip"

    req = request.Request(
        url=f"{config.server_url}/{path.lstrip('/')}",
        data=body,
        headers=request_headers,
        method=method,
    )
    context = build_ssl_context(config)
    try:
        with request.urlopen(req, timeout=config.request_timeout_seconds, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} calling {path}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Failed to reach {path}: {exc}") from exc


def register_agent(config: AgentConfig, agent_uuid_value: str) -> dict[str, Any]:
    if not config.enrollment_key:
        raise RuntimeError("Enrollment key is required until an API key has been issued")
    payload = build_registration_payload(config, agent_uuid_value)
    return http_json(config, "POST", "api/agents/register", payload)


def check_in_agent(
    config: AgentConfig,
    api_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    headers = {config.api_key_header: api_key}
    return http_json(config, "POST", "api/agents/check-in", payload, headers=headers, compress=True)


def merged_policy(state: dict[str, Any], response_policy: Optional[dict[str, Any]]) -> dict[str, Any]:
    policy = json.loads(canonical_json(DEFAULT_POLICY))
    cached = state.get("policy") or {}
    for source in (cached, response_policy or {}):
        if not source:
            continue
        for key, value in source.items():
            policy[key] = value
    if "enabled_commands" not in policy or not isinstance(policy["enabled_commands"], dict):
        policy["enabled_commands"] = json.loads(canonical_json(DEFAULT_POLICY["enabled_commands"]))
    return policy


def run_agent(
    config: AgentConfig,
    force: bool,
    register_only: bool = False,
    check_in_only: bool = False,
) -> int:
    ensure_state_dir(config.state_dir)
    state = read_json_file(state_file_path(config), default={})
    agent_uuid_value = ensure_agent_uuid(config)
    api_key = read_text_file(api_key_path(config))
    policy = merged_policy(state, None)

    registration_response = None
    if check_in_only and not api_key:
        raise RuntimeError(
            "Check-in-only mode requires an existing local agent API key"
        )

    if not api_key and not check_in_only:
        LOG.info("No agent API key found; registering agent %s", agent_uuid_value)
        registration_response = register_agent(config, agent_uuid_value)
        policy = merged_policy(state, registration_response.get("policy"))
        state["policy"] = policy
        state["agent_id"] = registration_response.get("agent", {}).get("id")
        state["enrollment_state"] = registration_response.get("agent", {}).get("enrollment_state")

        if registration_response.get("status") != "active":
            write_json_file(state_file_path(config), state)
            LOG.info(
                "Agent %s is %s; waiting for admin approval",
                agent_uuid_value,
                registration_response.get("status"),
            )
            return 0

        issued_api_key = registration_response.get("api_key")
        if not issued_api_key:
            raise RuntimeError(
                "Agent is active but no API key was returned. If the key was lost, "
                "an admin-side key rotation endpoint is needed."
            )
        write_text_file(api_key_path(config), issued_api_key)
        api_key = issued_api_key

    if register_only:
        state["policy"] = policy
        write_json_file(state_file_path(config), state)
        LOG.info("Register-only mode complete for %s", agent_uuid_value)
        return 0

    if not should_run_with_policy(state, policy, config.timer_interval_seconds, force):
        LOG.info("Skipping collection; cached policy interval has not elapsed")
        return 0

    sleep_delay = maybe_sleep_for_policy_jitter(policy)
    state["last_jitter_seconds"] = sleep_delay

    current_snapshot = build_current_snapshot(policy)
    previous_snapshot = state.get("last_snapshot") or {}
    delta_snapshot, full_snapshot = build_delta(current_snapshot, previous_snapshot)
    state["sequence_number"] = int(state.get("sequence_number", 0)) + 1

    payload = {
        "agent_uuid": agent_uuid_value,
        "observed_at": iso_now(),
        "sequence_number": state["sequence_number"],
        "full_snapshot": full_snapshot,
        "hostname": config.hostname or socket.gethostname(),
        "agent_version": AGENT_VERSION,
        "platform": platform.system().lower(),
        "platform_release": platform.release(),
        "metadata": {
            "runtime": "python-stdlib",
            "delta_mode": "set-diff",
        },
        "addresses": delta_snapshot["addresses"],
        "neighbors": delta_snapshot["neighbors"],
        "connections": delta_snapshot["connections"],
        "routes": delta_snapshot["routes"],
    }

    response = check_in_agent(config, api_key, payload)
    state["policy"] = merged_policy(state, response.get("policy"))
    state["last_snapshot"] = current_snapshot
    state["last_successful_checkin_at"] = response.get("server_time", iso_now())
    state["last_checkin_summary"] = response.get("summary", {})
    write_json_file(state_file_path(config), state)

    LOG.info(
        "Check-in accepted for %s: %s",
        agent_uuid_value,
        json.dumps(response.get("summary", {}), sort_keys=True),
    )
    return 0


def should_run_with_policy(
    state: dict[str, Any],
    policy: dict[str, Any],
    timer_interval_seconds: int,
    force: bool,
) -> bool:
    if force:
        return True
    last_success = state.get("last_successful_checkin_at")
    if not last_success:
        return True
    last_success_dt = parse_timestamp(last_success)
    if not last_success_dt:
        return True
    elapsed = (utcnow() - last_success_dt).total_seconds()
    desired_interval = int(
        policy.get("checkin_interval_seconds", DEFAULT_POLICY["checkin_interval_seconds"])
    )
    if desired_interval <= timer_interval_seconds:
        return True
    return elapsed >= desired_interval


def maybe_sleep_for_policy_jitter(policy: dict[str, Any]) -> int:
    jitter_seconds = int(policy.get("jitter_seconds", 0) or 0)
    if jitter_seconds <= 0:
        return 0
    delay = random.randint(0, jitter_seconds)
    if delay > 0:
        LOG.info("Sleeping %ss of policy jitter before collection", delay)
        time.sleep(delay)
    return delay


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = build_config(args)
        return run_agent(
            config,
            force=args.force,
            register_only=args.register_only,
            check_in_only=args.check_in_only,
        )
    except Exception as exc:  # noqa: BLE001
        LOG.error("%s", exc)
        LOG.debug("Passive agent failure", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
