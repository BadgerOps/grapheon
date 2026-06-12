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
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from ipaddress import ip_address, ip_network
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
        "topology_evidence": True,
    },
}

DEFAULT_STATE_DIR = "/var/lib/grapheon-agent"
DEFAULT_CONFIG_PATH = "/etc/grapheon-agent.env"
DEFAULT_TIMER_INTERVAL_SECONDS = 15
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_API_KEY_HEADER = "X-Agent-Api-Key"
STATE_FILENAME = "state.json"
AGENT_UUID_FILENAME = "agent_uuid"
API_KEY_FILENAME = "api_key"
DEFAULT_LOCAL_INTERFACE_PATTERNS = (
    "lo",
    "vmnet*",
    "vboxnet*",
    "docker*",
    "br-*",
    "virbr*",
    "veth*",
    "podman*",
    "cni*",
    "flannel*",
)
LLDP_ETHERTYPE = 0x88CC
CDP_DEST_MACS = {b"\x01\x00\x0c\xcc\xcc\xcc", b"\x01\x00\x0c\xcc\xcc\xcd"}
CDP_SNAP_HEADER = b"\xaa\xaa\x03\x00\x00\x0c\x20\x00"
STP_DEST_MACS = {b"\x01\x80\xc2\x00\x00\x00", b"\x01\x00\x0c\xcc\xcc\xcd"}
LACP_ETHERTYPE = 0x8809
DHCPV6_PORTS = {546, 547}
DISCOVERY_PORTS = {1900, 3702}
ROUTING_PROTOCOLS = {88: "eigrp", 89: "ospf", 112: "vrrp"}
CDP_CAPABILITIES = {
    0x01: "router",
    0x02: "transparent_bridge",
    0x04: "source_route_bridge",
    0x08: "switch",
    0x10: "host",
    0x20: "igmp",
    0x40: "repeater",
    0x80: "phone",
}
LLDP_CAPABILITIES = {
    0x0001: "other",
    0x0002: "repeater",
    0x0004: "bridge",
    0x0008: "wlan_ap",
    0x0010: "router",
    0x0020: "telephone",
    0x0040: "docsis",
    0x0080: "station",
    0x0100: "cvlan",
    0x0200: "svlan",
    0x0400: "tpmr",
}
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
    /usr/bin/env python3 /opt/grapheon/agent/current/grapheon_agent.py --config /etc/grapheon-agent.env --force
"""


def _load_agent_version() -> str:
    version_path = Path(__file__).with_name("VERSION")
    try:
        return version_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0-dev"


AGENT_VERSION = _load_agent_version()
DEFAULT_USER_AGENT = f"Grapheon-Agent/{AGENT_VERSION} python-urllib"


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
    user_agent: str
    ignore_local_net: bool
    dhcp_lease_paths: list[str] = None
    dns_log_paths: list[str] = None
    zeek_log_dir: Optional[str] = None
    topology_evidence_paths: list[str] = None
    topology_source_intervals: dict[str, int] = None
    topology_ignore_filters: list[str] = None
    topology_evidence_max_records: int = 1000
    passive_capture_enabled: bool = False
    passive_capture_duration_seconds: int = 60
    passive_capture_max_bytes: int = 5 * 1024 * 1024
    passive_capture_interfaces: list[str] = None
    passive_capture_include_flows: bool = False
    passive_capture_packet_limit: int = 2000


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
        "--user-agent",
        default=os.environ.get("GRAPHEON_AGENT_USER_AGENT"),
        help="HTTP User-Agent header sent to the Graphēon server",
    )
    parser.add_argument(
        "--ignore-local-net",
        action="store_true",
        default=None,
        help=(
            "Drop local-only network data such as loopback, link-local IPs, "
            "and common local virtualization bridge interfaces"
        ),
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


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_json_object(name: str) -> dict[str, Any]:
    raw = os.environ.get(name)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        LOG.warning("Ignoring invalid JSON in %s", name)
        return {}
    return value if isinstance(value, dict) else {}


def build_config(args: argparse.Namespace) -> AgentConfig:
    config_path = Path(args.config)
    load_env_file(config_path)

    server_url = args.server_url or os.environ.get("GRAPHEON_AGENT_SERVER_URL")
    enrollment_key = args.enrollment_key or os.environ.get("GRAPHEON_AGENT_ENROLLMENT_KEY")
    display_name = args.display_name or os.environ.get("GRAPHEON_AGENT_DISPLAY_NAME")
    site_name = args.site_name or os.environ.get("GRAPHEON_AGENT_SITE_NAME")
    hostname = args.hostname or os.environ.get("GRAPHEON_AGENT_HOSTNAME")
    ca_file = args.ca_file or os.environ.get("GRAPHEON_AGENT_CA_FILE")
    user_agent = args.user_agent or os.environ.get("GRAPHEON_AGENT_USER_AGENT") or DEFAULT_USER_AGENT
    ignore_local_net = (
        args.ignore_local_net
        if args.ignore_local_net is not None
        else _env_bool("GRAPHEON_AGENT_IGNORE_LOCAL_NET", False)
    )
    topology_max_records = int(os.environ.get("GRAPHEON_AGENT_TOPOLOGY_EVIDENCE_MAX_RECORDS", "1000"))
    capture_duration = int(os.environ.get("GRAPHEON_AGENT_PASSIVE_CAPTURE_DURATION_SECONDS", "60"))
    capture_max_bytes = int(os.environ.get("GRAPHEON_AGENT_PASSIVE_CAPTURE_MAX_BYTES", str(5 * 1024 * 1024)))

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
        user_agent=user_agent,
        ignore_local_net=ignore_local_net,
        dhcp_lease_paths=_env_list("GRAPHEON_AGENT_DHCP_LEASE_PATHS"),
        dns_log_paths=_env_list("GRAPHEON_AGENT_DNS_LOG_PATHS"),
        zeek_log_dir=os.environ.get("GRAPHEON_AGENT_ZEEK_LOG_DIR") or None,
        topology_evidence_paths=_env_list("GRAPHEON_AGENT_TOPOLOGY_EVIDENCE_PATHS"),
        topology_source_intervals={
            str(key): int(value)
            for key, value in _env_json_object("GRAPHEON_AGENT_TOPOLOGY_SOURCE_INTERVALS").items()
            if str(value).isdigit()
        },
        topology_ignore_filters=_env_list("GRAPHEON_AGENT_TOPOLOGY_IGNORE_FILTERS"),
        topology_evidence_max_records=max(0, topology_max_records),
        passive_capture_enabled=_env_bool("GRAPHEON_AGENT_PASSIVE_CAPTURE_ENABLED", False),
        passive_capture_duration_seconds=min(max(1, capture_duration), 300),
        passive_capture_max_bytes=min(max(65536, capture_max_bytes), 50 * 1024 * 1024),
        passive_capture_interfaces=_env_list("GRAPHEON_AGENT_PASSIVE_CAPTURE_INTERFACES"),
        passive_capture_include_flows=_env_bool("GRAPHEON_AGENT_PASSIVE_CAPTURE_INCLUDE_FLOWS", False),
        passive_capture_packet_limit=max(
            1,
            int(os.environ.get("GRAPHEON_AGENT_PASSIVE_CAPTURE_PACKET_LIMIT", "2000")),
        ),
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


def build_snapshot_payload(
    current: dict[str, list[dict[str, Any]]],
    previous: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, list[dict[str, Any]]], bool]:
    return current, True


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


def is_local_noise_interface(interface: Optional[str]) -> bool:
    if not interface:
        return False
    return any(fnmatch(interface, pattern) for pattern in DEFAULT_LOCAL_INTERFACE_PATTERNS)


def is_local_noise_ip(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        parsed = ip_address(value)
    except ValueError:
        try:
            network = ip_network(value, strict=False)
        except ValueError:
            return False
        return (
            network.is_loopback
            or network.is_link_local
            or network.is_multicast
            or network.is_reserved
            or network.is_unspecified
        )
    return (
        parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    )


def filter_local_net_records(
    records: list[dict[str, Any]],
    *,
    ip_fields: Iterable[str],
    interface_field: str = "interface",
) -> list[dict[str, Any]]:
    filtered = []
    for record in records:
        if is_local_noise_interface(record.get(interface_field)):
            continue
        if any(is_local_noise_ip(record.get(field)) for field in ip_fields):
            continue
        filtered.append(record)
    return canonicalize_entries(filtered)


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


def mac_bytes_to_text(value: bytes) -> str:
    return ":".join(f"{byte:02x}" for byte in value)


def clean_text(value: bytes) -> str:
    return value.decode("utf-8", errors="replace").strip("\x00\r\n\t ")


def schema_safe_name(value: str) -> tuple[str, Optional[str]]:
    raw = value.strip().rstrip(".")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)
    if not safe:
        safe = "unnamed"
    truncated = safe[:255]
    return truncated, raw if raw != truncated else None


def metadata_record(**items: Any) -> dict[str, Any]:
    cleaned = {}
    for key, value in items.items():
        if value is None:
            continue
        if value == "" or value == [] or value == {}:
            continue
        cleaned[key] = value
    return cleaned


def merge_metadata(record: dict[str, Any], **items: Any) -> dict[str, Any]:
    metadata = dict(record.get("metadata") or {})
    metadata.update(metadata_record(**items))
    if metadata:
        record["metadata"] = metadata
    return record


def capability_names(mask: int, lookup: dict[int, str]) -> list[str]:
    return [name for bit, name in lookup.items() if mask & bit]


def decode_lldp_org_tlv(value: bytes, metadata: dict[str, Any]) -> None:
    if len(value) < 4:
        return
    oui = value[:3]
    subtype = value[3]
    body = value[4:]
    if oui == b"\x00\x80\xc2":
        if subtype == 1 and len(body) >= 2:
            metadata["native_vlan"] = int.from_bytes(body[:2], "big")
        elif subtype == 3 and len(body) >= 3:
            vlan_id = int.from_bytes(body[:2], "big")
            vlan_name = clean_text(body[2:])
            metadata.setdefault("vlans", []).append({"vlan_id": vlan_id, "vlan_name": vlan_name})
        elif subtype == 7 and len(body) >= 5:
            metadata["link_aggregation"] = {
                "status": body[0],
                "port_id": int.from_bytes(body[1:5], "big"),
            }
    elif oui == b"\x00\x12\x0f" and subtype == 4 and len(body) >= 2:
        metadata["mtu"] = int.from_bytes(body[:2], "big")


def decode_lldp_id(subtype: int, value: bytes) -> str:
    if subtype == 4 and len(value) == 6:
        return mac_bytes_to_text(value)
    try:
        return value.decode("utf-8", errors="replace").strip("\x00")
    except UnicodeDecodeError:
        return value.hex()


def parse_lldp_frame(frame: bytes, interface: Optional[str] = None) -> Optional[dict[str, Any]]:
    if len(frame) < 14:
        return None
    ether_type = int.from_bytes(frame[12:14], "big")
    offset = 14
    if ether_type == 0x8100 and len(frame) >= 18:
        ether_type = int.from_bytes(frame[16:18], "big")
        offset = 18
    if ether_type != LLDP_ETHERTYPE:
        return None
    record: dict[str, Any] = {
        "evidence_type": "l2_neighbor",
        "source": "lldp",
        "confidence": 90,
        "interface": interface,
    }
    metadata: dict[str, Any] = {}
    while offset + 2 <= len(frame):
        header = int.from_bytes(frame[offset : offset + 2], "big")
        offset += 2
        tlv_type = (header >> 9) & 0x7F
        tlv_len = header & 0x1FF
        value = frame[offset : offset + tlv_len]
        offset += tlv_len
        if tlv_type == 0:
            break
        if not value:
            continue
        if tlv_type == 1:
            metadata["chassis_id_subtype"] = value[0]
            record["chassis_id"] = decode_lldp_id(value[0], value[1:])
        elif tlv_type == 2:
            metadata["port_id_subtype"] = value[0]
            record["port_id"] = decode_lldp_id(value[0], value[1:])
        elif tlv_type == 4:
            record["port_description"] = clean_text(value)
        elif tlv_type == 5:
            record["system_name"] = clean_text(value)
        elif tlv_type == 6:
            metadata["system_description"] = clean_text(value)
        elif tlv_type == 7 and len(value) >= 4:
            supported = int.from_bytes(value[:2], "big")
            enabled = int.from_bytes(value[2:4], "big")
            metadata["system_capabilities"] = capability_names(supported, LLDP_CAPABILITIES)
            metadata["enabled_capabilities"] = capability_names(enabled, LLDP_CAPABILITIES)
        elif tlv_type == 8 and len(value) >= 7:
            address_len = value[0]
            subtype = value[1]
            address = value[2 : 2 + max(address_len - 1, 0)]
            if subtype == 1 and len(address) == 4:
                record["management_ip"] = ".".join(str(byte) for byte in address)
            elif subtype == 2 and len(address) == 16:
                record["management_ip"] = str(ip_address(address))
        elif tlv_type == 127:
            decode_lldp_org_tlv(value, metadata)
    if "native_vlan" in metadata:
        record["vlan_id"] = metadata["native_vlan"]
    if metadata.get("vlans"):
        first_vlan = metadata["vlans"][0]
        record.setdefault("vlan_id", first_vlan.get("vlan_id"))
        record.setdefault("vlan_name", first_vlan.get("vlan_name"))
    merge_metadata(record, **metadata)
    if record.get("chassis_id") or record.get("system_name") or record.get("port_id"):
        return {key: value for key, value in record.items() if value is not None}
    return None


def parse_cdp_frame(frame: bytes, interface: Optional[str] = None) -> Optional[dict[str, Any]]:
    if len(frame) < 22 or frame[:6] not in CDP_DEST_MACS:
        return None
    payload_offset = frame.find(CDP_SNAP_HEADER, 14)
    if payload_offset < 0:
        return None
    offset = payload_offset + len(CDP_SNAP_HEADER)
    if offset + 4 > len(frame):
        return None
    offset += 4
    record: dict[str, Any] = {
        "evidence_type": "l2_neighbor",
        "source": "cdp",
        "confidence": 85,
        "interface": interface,
    }
    metadata: dict[str, Any] = {}
    while offset + 4 <= len(frame):
        tlv_type = int.from_bytes(frame[offset : offset + 2], "big")
        tlv_len = int.from_bytes(frame[offset + 2 : offset + 4], "big")
        if tlv_len < 4 or offset + tlv_len > len(frame):
            break
        value = frame[offset + 4 : offset + tlv_len]
        offset += tlv_len
        text = clean_text(value)
        if tlv_type == 0x0001:
            record["system_name"] = text
            record["chassis_id"] = text
        elif tlv_type == 0x0003:
            record["port_id"] = text
        elif tlv_type == 0x0004 and len(value) >= 4:
            mask = int.from_bytes(value[-4:], "big")
            metadata["capabilities"] = capability_names(mask, CDP_CAPABILITIES)
        elif tlv_type == 0x0005:
            metadata["software_version"] = text
        elif tlv_type == 0x0006:
            metadata["platform"] = text
        elif tlv_type == 0x000a and len(value) >= 2:
            vlan_id = int.from_bytes(value[:2], "big")
            record["vlan_id"] = vlan_id
            metadata["native_vlan"] = vlan_id
        elif tlv_type == 0x000b and value:
            metadata["duplex"] = "full" if value[-1] else "half"
        elif tlv_type == 0x0002 and len(value) >= 4:
            address_count = int.from_bytes(value[:4], "big")
            address_offset = 4
            for _ in range(address_count):
                if address_offset + 4 > len(value):
                    break
                protocol_type = value[address_offset]
                protocol_len = value[address_offset + 1]
                protocol = value[address_offset + 2 : address_offset + 2 + protocol_len]
                address_offset += 2 + protocol_len
                if address_offset + 2 > len(value):
                    break
                address_len = int.from_bytes(value[address_offset : address_offset + 2], "big")
                address_offset += 2
                address = value[address_offset : address_offset + address_len]
                address_offset += address_len
                if protocol_type == 1 and protocol == b"\xcc" and address_len == 4 and len(address) == 4:
                    record["management_ip"] = str(ip_address(address))
                    break
    merge_metadata(record, **metadata)
    if record.get("system_name") or record.get("port_id") or record.get("management_ip"):
        return {key: value for key, value in record.items() if value is not None}
    return None


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


def collect_addresses(timeout_seconds: int, ignore_local_net: bool = False) -> list[dict[str, Any]]:
    command = choose_command(["ip", "-json", "addr", "show"])
    if not command:
        LOG.warning("Skipping address collection: ip command not found")
        return []
    try:
        records = parse_ip_addr_json(run_command(command, timeout_seconds))
    except (subprocess.SubprocessError, OSError) as exc:
        LOG.warning("Address collection failed: %s", exc)
        return []
    if ignore_local_net:
        return filter_local_net_records(records, ip_fields=["ip_address"])
    return records


def collect_routes(timeout_seconds: int, ignore_local_net: bool = False) -> list[dict[str, Any]]:
    command = choose_command(["ip", "-json", "route", "show"])
    if not command:
        LOG.warning("Skipping route collection: ip command not found")
        return []
    try:
        records = parse_ip_route_json(run_command(command, timeout_seconds))
    except (subprocess.SubprocessError, OSError) as exc:
        LOG.warning("Route collection failed: %s", exc)
        return []
    if ignore_local_net:
        return filter_local_net_records(records, ip_fields=["destination", "gateway", "source_ip"])
    return records


def collect_neighbors(timeout_seconds: int, ignore_local_net: bool = False) -> list[dict[str, Any]]:
    command = choose_command(["ip", "-json", "neigh", "show"])
    if not command:
        LOG.warning("Skipping neighbor collection: ip command not found")
        return []
    try:
        records = parse_ip_neigh_json(run_command(command, timeout_seconds))
    except (subprocess.SubprocessError, OSError) as exc:
        LOG.warning("Neighbor collection failed: %s", exc)
        return []
    if ignore_local_net:
        return filter_local_net_records(records, ip_fields=["ip_address"])
    return records


def collect_connections(timeout_seconds: int, ignore_local_net: bool = False) -> list[dict[str, Any]]:
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
        records = parse_netstat_output(output)
    else:
        records = parse_ss_output(output)
    if ignore_local_net:
        return filter_local_net_records(records, ip_fields=["local_ip", "remote_ip"])
    return records


def parse_dns_name(payload: bytes, offset: int, depth: int = 0) -> tuple[Optional[str], int]:
    if depth > 8:
        return None, offset
    labels = []
    current = offset
    jumped = False
    next_offset = offset
    while current < len(payload):
        length = payload[current]
        current += 1
        if length == 0:
            if not jumped:
                next_offset = current
            return ".".join(labels), next_offset
        if length & 0xC0 == 0xC0:
            if current >= len(payload):
                return None, next_offset
            pointer = ((length & 0x3F) << 8) | payload[current]
            current += 1
            if not jumped:
                next_offset = current
            pointed, _ = parse_dns_name(payload, pointer, depth + 1)
            if pointed:
                labels.append(pointed)
            return ".".join(labels), next_offset
        if current + length > len(payload):
            return None, next_offset
        labels.append(payload[current : current + length].decode("utf-8", errors="replace"))
        current += length

    return None, next_offset


def reverse_dns_to_ip(name: str) -> Optional[str]:
    lower = name.rstrip(".").lower()
    if lower.endswith(".in-addr.arpa"):
        parts = lower.removesuffix(".in-addr.arpa").strip(".").split(".")
        if len(parts) == 4:
            try:
                return str(ip_address(".".join(reversed(parts))))
            except ValueError:
                return None
    if lower.endswith(".ip6.arpa"):
        nibbles = lower.removesuffix(".ip6.arpa").strip(".").split(".")
        if len(nibbles) == 32:
            try:
                hex_value = "".join(reversed(nibbles))
                return str(ip_address(":".join(hex_value[i : i + 4] for i in range(0, 32, 4))))
            except ValueError:
                return None
    return None


def parse_dns_rdata_name(payload: bytes, rdata_offset: int) -> Optional[str]:
    name, _ = parse_dns_name(payload, rdata_offset)
    return name.rstrip(".") if name else None


def parse_dns_evidence(
    payload: bytes,
    *,
    source: str,
    observer: Optional[str],
    src_ip: Optional[str] = None,
    vlan_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    if len(payload) < 12:
        return []
    flags = int.from_bytes(payload[2:4], "big")
    if not flags & 0x8000:
        return []
    qdcount = int.from_bytes(payload[4:6], "big")
    ancount = int.from_bytes(payload[6:8], "big")
    offset = 12
    for _ in range(qdcount):
        _, offset = parse_dns_name(payload, offset)
        offset += 4
        if offset > len(payload):
            return []
    records = []
    for _ in range(ancount):
        name, offset = parse_dns_name(payload, offset)
        if offset + 10 > len(payload):
            break
        rr_type = int.from_bytes(payload[offset : offset + 2], "big")
        rr_class = int.from_bytes(payload[offset + 2 : offset + 4], "big")
        ttl = int.from_bytes(payload[offset + 4 : offset + 8], "big")
        rdlength = int.from_bytes(payload[offset + 8 : offset + 10], "big")
        offset += 10
        rdata_offset = offset
        rdata = payload[offset : offset + rdlength]
        offset += rdlength
        if rr_class not in {1, 32769}:
            continue
        ip_value = None
        dns_name = name.rstrip(".") if name else None
        record_metadata = metadata_record(ttl=ttl, rr_type=rr_type, source_protocol=source, vlan_id=vlan_id)
        if rr_type == 1 and len(rdata) == 4:
            ip_value = str(ip_address(rdata))
        elif rr_type == 28 and len(rdata) == 16:
            ip_value = str(ip_address(rdata))
        elif rr_type in {2, 5, 12, 39}:
            target = parse_dns_rdata_name(payload, rdata_offset)
            ip_value = reverse_dns_to_ip(dns_name or "") or src_ip
            dns_name = target or dns_name
            record_metadata["record_target"] = target
        elif rr_type == 33 and len(rdata) >= 7:
            priority = int.from_bytes(rdata[0:2], "big")
            weight = int.from_bytes(rdata[2:4], "big")
            port = int.from_bytes(rdata[4:6], "big")
            target = parse_dns_rdata_name(payload, rdata_offset + 6)
            ip_value = src_ip
            record_metadata.update({"priority": priority, "weight": weight, "service_port": port, "record_target": target})
        elif rr_type in {64, 65} and len(rdata) >= 3:
            priority = int.from_bytes(rdata[0:2], "big")
            target = parse_dns_rdata_name(payload, rdata_offset + 2)
            ip_value = src_ip
            record_metadata.update({"priority": priority, "record_target": target, "record_kind": "svcb" if rr_type == 64 else "https"})
        if (ip_value or src_ip) and dns_name:
            safe_name, raw_name = schema_safe_name(dns_name)
            if raw_name:
                record_metadata["raw_name"] = raw_name
            records.append(
                {
                    "evidence_type": "dns_name",
                    "source": source,
                    "observer": observer,
                    "confidence": 70 if source in {"mdns", "llmnr"} else 75,
                    "ip_address": ip_value or src_ip,
                    "name": safe_name,
                    "vlan_id": vlan_id,
                    "metadata": record_metadata,
                }
            )
    return records


def parse_dhcp_evidence(
    payload: bytes,
    *,
    observer: Optional[str],
    vlan_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    if len(payload) < 240 or payload[236:240] != b"\x63\x82\x53\x63":
        return []
    hlen = payload[2]
    if hlen <= 0 or hlen > 16:
        return []
    yiaddr = str(ip_address(payload[16:20]))
    ciaddr = str(ip_address(payload[12:16]))
    chaddr = mac_bytes_to_text(payload[28 : 28 + min(hlen, 6)])
    options = {}
    offset = 240
    while offset < len(payload):
        code = payload[offset]
        offset += 1
        if code == 255:
            break
        if code == 0:
            continue
        if offset >= len(payload):
            break
        length = payload[offset]
        offset += 1
        value = payload[offset : offset + length]
        offset += length
        options[code] = value

    ip_value = yiaddr if yiaddr != "0.0.0.0" else ciaddr
    if ip_value == "0.0.0.0" and 50 in options and len(options[50]) == 4:
        ip_value = str(ip_address(options[50]))
    if ip_value == "0.0.0.0":
        return []
    hostname = clean_text(options.get(12, b"")) or None
    metadata = {
        "message_type": options.get(53, b"").hex() or None,
        "server_id": str(ip_address(options[54])) if len(options.get(54, b"")) == 4 else None,
        "lease_time_seconds": int.from_bytes(options[51], "big") if len(options.get(51, b"")) == 4 else None,
        "router": str(ip_address(options[3][:4])) if len(options.get(3, b"")) >= 4 else None,
        "routers": [str(ip_address(options[3][idx : idx + 4])) for idx in range(0, len(options.get(3, b"")), 4)]
        if len(options.get(3, b"")) >= 4 and len(options.get(3, b"")) % 4 == 0
        else None,
        "subnet_mask": str(ip_address(options[1])) if len(options.get(1, b"")) == 4 else None,
        "dns_servers": [str(ip_address(options[6][idx : idx + 4])) for idx in range(0, len(options.get(6, b"")), 4)]
        if len(options.get(6, b"")) >= 4 and len(options.get(6, b"")) % 4 == 0
        else None,
        "domain": clean_text(options.get(15, b"")) or None,
        "vendor_class": clean_text(options.get(60, b"")) or None,
        "client_id": options.get(61, b"").hex() or None,
        "fqdn": clean_text(options.get(81, b"")[3:] if len(options.get(81, b"")) > 3 else options.get(81, b"")) or None,
        "requested_ip": str(ip_address(options[50])) if len(options.get(50, b"")) == 4 else None,
        "relay_agent": options.get(82, b"").hex() or None,
        "vlan_id": vlan_id,
    }
    return [
        {
            "evidence_type": "dhcp_lease",
            "source": "dhcp",
            "observer": observer,
            "confidence": 90,
            "ip_address": ip_value,
            "mac_address": chaddr,
            "hostname": hostname,
            "fqdn": metadata.get("fqdn"),
            "vlan_id": vlan_id,
            "metadata": metadata_record(**metadata),
        }
    ]


def parse_dhcpv6_options(payload: bytes, offset: int = 0, end: Optional[int] = None) -> list[tuple[int, bytes]]:
    options = []
    end = len(payload) if end is None else min(end, len(payload))
    while offset + 4 <= end:
        code = int.from_bytes(payload[offset : offset + 2], "big")
        length = int.from_bytes(payload[offset + 2 : offset + 4], "big")
        offset += 4
        value = payload[offset : offset + length]
        offset += length
        if len(value) == length:
            options.append((code, value))
    return options


def parse_domain_search(value: bytes) -> list[str]:
    names = []
    offset = 0
    while offset < len(value):
        name, next_offset = parse_dns_name(value, offset)
        if not name or next_offset <= offset:
            break
        names.append(name.rstrip("."))
        offset = next_offset
    return names


def duid_mac(value: bytes) -> Optional[str]:
    if len(value) >= 10 and int.from_bytes(value[:2], "big") == 1:
        return mac_bytes_to_text(value[-6:])
    if len(value) >= 8 and int.from_bytes(value[:2], "big") == 3:
        return mac_bytes_to_text(value[-6:])
    return None


def parse_dhcpv6_evidence(
    payload: bytes,
    *,
    observer: Optional[str],
    src_ip: Optional[str],
    vlan_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    if len(payload) < 4:
        return []
    message_type = payload[0]
    transaction_id = payload[1:4].hex()
    options = parse_dhcpv6_options(payload, 4)
    metadata: dict[str, Any] = {
        "message_type": message_type,
        "transaction_id": transaction_id,
        "vlan_id": vlan_id,
    }
    client_duid = None
    server_duid = None
    hostname = None
    dns_servers = []
    search_domains = []
    lease_records = []
    prefixes = []

    for code, value in options:
        if code == 1:
            client_duid = value.hex()
            metadata["client_duid"] = client_duid
        elif code == 2:
            server_duid = value.hex()
            metadata["server_duid"] = server_duid
        elif code == 23 and len(value) >= 16:
            dns_servers.extend(str(ip_address(value[idx : idx + 16])) for idx in range(0, len(value), 16) if len(value[idx : idx + 16]) == 16)
        elif code == 24:
            search_domains.extend(parse_domain_search(value))
        elif code == 39:
            hostname = clean_text(value[1:] if value else value) or None
        elif code in {3, 25} and len(value) >= 12:
            iaid = value[:4].hex()
            sub_options = parse_dhcpv6_options(value, 12)
            for sub_code, sub_value in sub_options:
                if sub_code == 5 and len(sub_value) >= 24:
                    lease_records.append(
                        {
                            "iaid": iaid,
                            "ip_address": str(ip_address(sub_value[:16])),
                            "preferred_lifetime": int.from_bytes(sub_value[16:20], "big"),
                            "valid_lifetime": int.from_bytes(sub_value[20:24], "big"),
                        }
                    )
                elif sub_code == 26 and len(sub_value) >= 25:
                    prefix_len = sub_value[8]
                    prefix_ip = ip_address(sub_value[9:25])
                    if prefix_ip:
                        prefixes.append(
                            {
                                "iaid": iaid,
                                "prefix": f"{prefix_ip}/{prefix_len}",
                                "preferred_lifetime": int.from_bytes(sub_value[16:20], "big"),
                                "valid_lifetime": int.from_bytes(sub_value[20:24], "big"),
                            }
                        )

    metadata.update(metadata_record(dns_servers=dns_servers, search_domains=search_domains, prefixes=prefixes, server_duid=server_duid))
    mac = duid_mac(bytes.fromhex(client_duid)) if client_duid else None
    records = []
    for lease in lease_records:
        records.append(
            {
                "evidence_type": "dhcp_lease",
                "source": "dhcpv6",
                "observer": observer,
                "confidence": 85,
                "ip_address": lease["ip_address"],
                "mac_address": mac,
                "hostname": hostname,
                "vlan_id": vlan_id,
                "metadata": metadata_record(**metadata, **lease, source_ip=src_ip),
            }
        )
    for prefix in prefixes:
        records.append(
            {
                "evidence_type": "network_segment",
                "source": "dhcpv6",
                "observer": observer,
                "confidence": 70,
                "network": prefix["prefix"],
                "vlan_id": vlan_id,
                "metadata": metadata_record(**metadata, **prefix, source_ip=src_ip),
            }
        )
    return records


def parse_arp_evidence(payload: bytes, observer: Optional[str]) -> list[dict[str, Any]]:
    if len(payload) < 28:
        return []
    htype, ptype, hlen, plen, _opcode = struct.unpack("!HHBBH", payload[:8])
    if htype != 1 or ptype != 0x0800 or hlen != 6 or plen != 4:
        return []
    sender_mac = mac_bytes_to_text(payload[8:14])
    sender_ip = str(ip_address(payload[14:18]))
    records = []
    if sender_ip != "0.0.0.0" and sender_mac != "00:00:00:00:00:00":
        records.append(
            {
                "evidence_type": "mac_ip_binding",
                "source": "agent",
                "observer": observer,
                "confidence": 85,
                "ip_address": sender_ip,
                "mac_address": sender_mac,
            }
        )
    target_mac = mac_bytes_to_text(payload[18:24])
    target_ip = str(ip_address(payload[24:28]))
    if target_ip != "0.0.0.0" and target_mac != "00:00:00:00:00:00":
        records.append(
            {
                "evidence_type": "mac_ip_binding",
                "source": "agent",
                "observer": observer,
                "confidence": 80,
                "ip_address": target_ip,
                "mac_address": target_mac,
            }
        )
    return records


def decode_nbns_name(value: bytes, offset: int) -> tuple[Optional[str], int]:
    if offset >= len(value):
        return None, offset
    length = value[offset]
    offset += 1
    if length != 32 or offset + 32 > len(value):
        return None, offset
    raw = bytearray()
    encoded = value[offset : offset + 32]
    offset += 32
    for idx in range(0, 32, 2):
        high = encoded[idx] - 0x41
        low = encoded[idx + 1] - 0x41
        if high < 0 or high > 15 or low < 0 or low > 15:
            return None, offset
        raw.append((high << 4) | low)
    if offset < len(value) and value[offset] == 0:
        offset += 1
    return raw[:15].decode("ascii", errors="replace").strip(), offset


def parse_nbns_evidence(
    payload: bytes,
    *,
    observer: Optional[str],
    src_ip: Optional[str],
    vlan_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    if len(payload) < 12:
        return []
    flags = int.from_bytes(payload[2:4], "big")
    qdcount = int.from_bytes(payload[4:6], "big")
    ancount = int.from_bytes(payload[6:8], "big")
    offset = 12
    names = []
    for _ in range(qdcount):
        name, offset = decode_nbns_name(payload, offset)
        if name:
            names.append(name)
        offset += 4
    records = []
    for _ in range(ancount):
        name, offset = decode_nbns_name(payload, offset)
        if offset + 10 > len(payload):
            break
        rr_type = int.from_bytes(payload[offset : offset + 2], "big")
        ttl = int.from_bytes(payload[offset + 4 : offset + 8], "big")
        rdlength = int.from_bytes(payload[offset + 8 : offset + 10], "big")
        offset += 10
        rdata = payload[offset : offset + rdlength]
        offset += rdlength
        if name:
            names.append(name)
        if rr_type == 0x20 and len(rdata) >= 6:
            ip_value = str(ip_address(rdata[-4:]))
        else:
            ip_value = src_ip
        for nb_name in sorted(set(names)):
            safe_name, raw_name = schema_safe_name(nb_name)
            records.append(
                {
                    "evidence_type": "dns_name",
                    "source": "nbns",
                    "observer": observer,
                    "confidence": 70 if flags & 0x8000 else 55,
                    "ip_address": ip_value,
                    "name": safe_name,
                    "vlan_id": vlan_id,
                    "metadata": metadata_record(ttl=ttl, rr_type=rr_type, source_protocol="nbns", vlan_id=vlan_id, raw_name=raw_name),
                }
            )
    return records


def parse_header_lines(payload: bytes) -> dict[str, str]:
    text = payload.decode("utf-8", errors="ignore")
    headers = {}
    for line in text.replace("\r\n", "\n").split("\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def parse_ssdp_evidence(payload: bytes, *, observer: Optional[str], src_ip: str, vlan_id: Optional[int] = None) -> list[dict[str, Any]]:
    headers = parse_header_lines(payload)
    if not headers:
        return []
    service_label = headers.get("usn") or headers.get("st") or headers.get("nt") or headers.get("server")
    if not service_label:
        return []
    return [
        {
            "evidence_type": "dns_name",
            "source": "ssdp",
            "observer": observer,
            "confidence": 55,
            "ip_address": src_ip,
            "name": f"ssdp-{src_ip.replace(':', '-')}"[:255],
            "vlan_id": vlan_id,
            "metadata": metadata_record(
                service_label=service_label,
                device_type=headers.get("st") or headers.get("nt"),
                usn=headers.get("usn"),
                location=headers.get("location"),
                server=headers.get("server"),
                vlan_id=vlan_id,
            ),
        }
    ]


def first_xml_text(text: str, names: Iterable[str]) -> Optional[str]:
    lower = text.lower()
    for name in names:
        tag = name.lower()
        start_token = f"<{tag}>"
        end_token = f"</{tag}>"
        start = lower.find(start_token)
        end = lower.find(end_token)
        if start >= 0 and end > start:
            return text[start + len(start_token) : end].strip()
    return None


def parse_wsd_evidence(payload: bytes, *, observer: Optional[str], src_ip: str, vlan_id: Optional[int] = None) -> list[dict[str, Any]]:
    text = payload.decode("utf-8", errors="ignore")
    if "http://schemas.xmlsoap.org/ws/2005/04/discovery" not in text and "ProbeMatch" not in text and "Hello" not in text:
        return []
    endpoint = first_xml_text(text, ["a:Address", "Address"])
    types = first_xml_text(text, ["d:Types", "Types"])
    xaddrs = first_xml_text(text, ["d:XAddrs", "XAddrs"])
    service_label = endpoint or types or xaddrs
    if not service_label:
        return []
    return [
        {
            "evidence_type": "dns_name",
            "source": "wsd",
            "observer": observer,
            "confidence": 55,
            "ip_address": src_ip,
            "name": f"wsd-{src_ip.replace(':', '-')}"[:255],
            "vlan_id": vlan_id,
            "metadata": metadata_record(service_label=service_label, endpoint=endpoint, types=types, xaddrs=xaddrs, vlan_id=vlan_id),
        }
    ]


def parse_stp_evidence(packet: bytes, *, observer: Optional[str], interface: Optional[str], vlan_id: Optional[int]) -> Optional[dict[str, Any]]:
    if packet[:6] not in STP_DEST_MACS:
        return None
    llc_offset = 18 if int.from_bytes(packet[12:14], "big") == 0x8100 else 14
    payload = packet[llc_offset:]
    if len(payload) < 38 or payload[:3] != b"\x42\x42\x03":
        return None
    bpdu = payload[3:]
    root_id = bpdu[5:13].hex(":")
    bridge_id = bpdu[17:25].hex(":")
    return {
        "evidence_type": "l2_neighbor",
        "source": "stp",
        "observer": observer,
        "confidence": 60,
        "interface": interface,
        "chassis_id": bridge_id,
        "vlan_id": vlan_id,
        "metadata": metadata_record(
            protocol_id=int.from_bytes(bpdu[:2], "big"),
            protocol_version=bpdu[2],
            bpdu_type=bpdu[3],
            root_bridge_id=root_id,
            bridge_id=bridge_id,
            root_path_cost=int.from_bytes(bpdu[13:17], "big"),
            port_id=bpdu[25:27].hex(),
            vlan_id=vlan_id,
        ),
    }


def parse_lacp_evidence(payload: bytes, *, observer: Optional[str], interface: Optional[str], vlan_id: Optional[int]) -> Optional[dict[str, Any]]:
    if len(payload) < 44 or payload[0] != 1:
        return None
    actor_system = mac_bytes_to_text(payload[6:12])
    partner_system = mac_bytes_to_text(payload[26:32]) if len(payload) >= 32 else None
    return {
        "evidence_type": "l2_neighbor",
        "source": "lacp",
        "observer": observer,
        "confidence": 65,
        "interface": interface,
        "chassis_id": partner_system or actor_system,
        "vlan_id": vlan_id,
        "metadata": metadata_record(
            actor_system=actor_system,
            actor_key=int.from_bytes(payload[14:16], "big"),
            actor_port=int.from_bytes(payload[18:20], "big"),
            partner_system=partner_system,
            partner_key=int.from_bytes(payload[34:36], "big") if len(payload) >= 36 else None,
            partner_port=int.from_bytes(payload[38:40], "big") if len(payload) >= 40 else None,
            vlan_id=vlan_id,
        ),
    }


def parse_icmpv6_evidence(
    payload: bytes,
    *,
    src_ip: str,
    observer: Optional[str],
    vlan_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    if len(payload) < 8:
        return []
    icmp_type = payload[0]
    records = []
    if icmp_type == 134:
        target_ip = src_ip
        router_lifetime = int.from_bytes(payload[6:8], "big") if len(payload) >= 8 else None
        records.append(
            {
                "evidence_type": "route",
                "source": "agent",
                "observer": observer,
                "confidence": 65,
                "destination": "default",
                "gateway": src_ip,
                "vlan_id": vlan_id,
                "metadata": metadata_record(router_lifetime_seconds=router_lifetime, vlan_id=vlan_id),
            }
        )
        offset = 16
    elif icmp_type in {135, 136} and len(payload) >= 24:
        target_ip = str(ip_address(payload[8:24]))
        offset = 24
    else:
        return records

    while offset + 2 <= len(payload):
        opt_type = payload[offset]
        opt_len = payload[offset + 1] * 8
        if opt_len <= 0 or offset + opt_len > len(payload):
            break
        value = payload[offset + 2 : offset + opt_len]
        if opt_type in {1, 2} and len(value) >= 6:
            mac = mac_bytes_to_text(value[:6])
            ip_value = target_ip if icmp_type in {135, 136} else src_ip
            records.append(
                {
                    "evidence_type": "mac_ip_binding",
                    "source": "agent",
                    "observer": observer,
                    "confidence": 70,
                    "ip_address": ip_value,
                    "mac_address": mac,
                    "vlan_id": vlan_id,
                    "metadata": metadata_record(source_protocol="icmpv6_nd", vlan_id=vlan_id),
                }
            )
        elif icmp_type == 134 and opt_type == 3 and len(value) >= 30:
            prefix_len = value[0]
            valid_lifetime = int.from_bytes(value[2:6], "big")
            preferred_lifetime = int.from_bytes(value[6:10], "big")
            prefix = str(ip_network(f"{ip_address(value[14:30])}/{prefix_len}", strict=False))
            records.append(
                {
                    "evidence_type": "network_segment",
                    "source": "agent",
                    "observer": observer,
                    "confidence": 70,
                    "network": prefix,
                    "vlan_id": vlan_id,
                    "metadata": metadata_record(
                        source_protocol="icmpv6_ra",
                        prefix_length=prefix_len,
                        valid_lifetime_seconds=valid_lifetime,
                        preferred_lifetime_seconds=preferred_lifetime,
                        vlan_id=vlan_id,
                    ),
                }
            )
        elif icmp_type == 134 and opt_type == 5 and len(value) >= 6:
            if records:
                merge_metadata(records[0], mtu=int.from_bytes(value[2:6], "big"))
        elif icmp_type == 134 and opt_type == 25 and len(value) >= 22:
            lifetime = int.from_bytes(value[2:6], "big")
            servers = [str(ip_address(value[idx : idx + 16])) for idx in range(6, len(value), 16) if len(value[idx : idx + 16]) == 16]
            if records:
                merge_metadata(records[0], rdnss=servers, rdnss_lifetime_seconds=lifetime)
        elif icmp_type == 134 and opt_type == 31 and len(value) >= 6:
            lifetime = int.from_bytes(value[2:6], "big")
            domains = parse_domain_search(value[6:])
            if records:
                merge_metadata(records[0], dnssl=domains, dnssl_lifetime_seconds=lifetime)
        offset += opt_len
    return records


def parse_ip_packet_evidence(
    payload: bytes,
    *,
    ether_type: int,
    observer: Optional[str],
    include_flows: bool,
    vlan_id: Optional[int] = None,
    captured_len: Optional[int] = None,
    packet_time: Optional[str] = None,
) -> list[dict[str, Any]]:
    if ether_type == 0x0800:
        if len(payload) < 20:
            return []
        ihl = (payload[0] & 0x0F) * 4
        protocol = payload[9]
        src_ip = str(ip_address(payload[12:16]))
        dst_ip = str(ip_address(payload[16:20]))
        transport = payload[ihl:]
    elif ether_type == 0x86DD:
        if len(payload) < 40:
            return []
        protocol = payload[6]
        src_ip = str(ip_address(payload[8:24]))
        dst_ip = str(ip_address(payload[24:40]))
        transport = payload[40:]
    else:
        return []

    if ether_type == 0x86DD and protocol == 58:
        return parse_icmpv6_evidence(transport, src_ip=src_ip, observer=observer, vlan_id=vlan_id)

    if protocol in ROUTING_PROTOCOLS:
        routing_protocol = ROUTING_PROTOCOLS[protocol]
        metadata = metadata_record(
            routing_protocol=routing_protocol,
            source_ip=src_ip,
            destination_ip=dst_ip,
            captured_len=captured_len,
            vlan_id=vlan_id,
        )
        if routing_protocol == "ospf" and len(transport) >= 16:
            metadata.update(
                {
                    "ospf_version": transport[0],
                    "ospf_type": transport[1],
                    "router_id": str(ip_address(transport[4:8])),
                    "area_id": str(ip_address(transport[8:12])),
                }
            )
        elif routing_protocol == "eigrp" and len(transport) >= 12:
            metadata.update({"eigrp_version": transport[0], "eigrp_opcode": transport[1], "asn": int.from_bytes(transport[8:12], "big")})
        elif routing_protocol == "vrrp" and len(transport) >= 8:
            version = transport[0] >> 4
            vrid = transport[1]
            priority = transport[2]
            address_count = transport[3]
            addresses = []
            if version == 2 and len(transport) >= 8 + (address_count * 4):
                addresses = [str(ip_address(transport[8 + idx : 12 + idx])) for idx in range(0, address_count * 4, 4)]
            metadata.update({"version": version, "vrid": vrid, "priority": priority, "virtual_addresses": addresses})
            if version not in {2, 3}:
                routing_protocol = "carp"
                metadata["routing_protocol"] = "carp"
        return [
            {
                "evidence_type": "route",
                "source": routing_protocol,
                "observer": observer,
                "confidence": 45,
                "source_ip": src_ip,
                "gateway": src_ip,
                "destination": "routing-adjacency",
                "vlan_id": vlan_id,
                "metadata": metadata,
            }
        ]

    if protocol not in {6, 17} or len(transport) < 4:
        return []
    src_port, dst_port = struct.unpack("!HH", transport[:4])
    records = []
    app_payload = b""
    proto_name = "tcp" if protocol == 6 else "udp"
    tcp_flags = None
    if protocol == 17 and len(transport) >= 8:
        app_payload = transport[8:]
    elif protocol == 6 and len(transport) >= 20:
        data_offset = (transport[12] >> 4) * 4
        tcp_flags = transport[13]
        app_payload = transport[data_offset:]

    ports = {src_port, dst_port}
    if ports & {67, 68} and protocol == 17:
        records.extend(parse_dhcp_evidence(app_payload, observer=observer, vlan_id=vlan_id))
    if ports & DHCPV6_PORTS and protocol == 17:
        records.extend(parse_dhcpv6_evidence(app_payload, observer=observer, src_ip=src_ip, vlan_id=vlan_id))
    if 137 in ports and protocol == 17:
        records.extend(parse_nbns_evidence(app_payload, observer=observer, src_ip=src_ip, vlan_id=vlan_id))
    elif ports & {53, 5353, 5355}:
        source = "dns"
        if 5353 in ports:
            source = "mdns"
        elif 5355 in ports:
            source = "llmnr"
        records.extend(parse_dns_evidence(app_payload, source=source, observer=observer, src_ip=src_ip, vlan_id=vlan_id))
    if 1900 in ports and protocol == 17:
        records.extend(parse_ssdp_evidence(app_payload, observer=observer, src_ip=src_ip, vlan_id=vlan_id))
    if 3702 in ports and protocol == 17:
        records.extend(parse_wsd_evidence(app_payload, observer=observer, src_ip=src_ip, vlan_id=vlan_id))
    if 1985 in ports and protocol == 17 and len(app_payload) >= 20:
        virtual_ip = str(ip_address(app_payload[16:20]))
        records.append(
            {
                "evidence_type": "route",
                "source": "hsrp",
                "observer": observer,
                "confidence": 60,
                "source_ip": src_ip,
                "gateway": virtual_ip,
                "destination": "default",
                "vlan_id": vlan_id,
                "metadata": metadata_record(version=app_payload[0], opcode=app_payload[1], state=app_payload[2], group=app_payload[5], vlan_id=vlan_id),
            }
        )
    if ports & {520, 521} and protocol == 17:
        records.append(
            {
                "evidence_type": "route",
                "source": "rip",
                "observer": observer,
                "confidence": 40,
                "source_ip": src_ip,
                "gateway": src_ip,
                "destination": "routing-update",
                "vlan_id": vlan_id,
                "metadata": metadata_record(command=app_payload[0] if app_payload else None, version=app_payload[1] if len(app_payload) > 1 else None, vlan_id=vlan_id),
            }
        )
    if 179 in ports and protocol == 6:
        records.append(
            {
                "evidence_type": "flow_relationship",
                "source": "bgp",
                "observer": observer,
                "confidence": 55,
                "local_ip": src_ip,
                "local_port": src_port,
                "remote_ip": dst_ip,
                "remote_port": dst_port,
                "protocol": "tcp",
                "vlan_id": vlan_id,
                "metadata": metadata_record(service="bgp", vlan_id=vlan_id),
            }
        )

    topology_ports = {53, 67, 68, 137, 546, 547, 1900, 1985, 3702, 520, 521, 5353, 5355}
    if include_flows and not (ports & topology_ports):
        records.append(
            {
                "evidence_type": "flow_relationship",
                "source": "agent",
                "observer": observer,
                "confidence": 25,
                "local_ip": src_ip,
                "local_port": src_port,
                "remote_ip": dst_ip,
                "remote_port": dst_port,
                "protocol": proto_name,
                "vlan_id": vlan_id,
                "first_seen": packet_time,
                "last_seen": packet_time,
                "metadata": metadata_record(
                    packet_count=1,
                    byte_count=captured_len,
                    tcp_flags=tcp_flags,
                    tcp_syn=bool(tcp_flags & 0x02) if tcp_flags is not None else None,
                    tcp_ack=bool(tcp_flags & 0x10) if tcp_flags is not None else None,
                    direction="observed",
                    vlan_id=vlan_id,
                ),
            }
        )
    return records


def aggregate_flow_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregated: dict[tuple[Any, ...], dict[str, Any]] = {}
    output = []
    for record in records:
        if record.get("evidence_type") != "flow_relationship" or record.get("source") != "agent":
            output.append(record)
            continue
        key = (
            record.get("local_ip"),
            record.get("local_port"),
            record.get("remote_ip"),
            record.get("remote_port"),
            record.get("protocol"),
            record.get("vlan_id"),
        )
        metadata = dict(record.get("metadata") or {})
        existing = aggregated.get(key)
        if not existing:
            existing = dict(record)
            existing["metadata"] = dict(metadata)
            aggregated[key] = existing
            continue
        existing_metadata = existing.setdefault("metadata", {})
        existing_metadata["packet_count"] = int(existing_metadata.get("packet_count") or 0) + int(metadata.get("packet_count") or 1)
        existing_metadata["byte_count"] = int(existing_metadata.get("byte_count") or 0) + int(metadata.get("byte_count") or 0)
        existing_metadata["tcp_syn"] = bool(existing_metadata.get("tcp_syn") or metadata.get("tcp_syn"))
        existing_metadata["tcp_ack"] = bool(existing_metadata.get("tcp_ack") or metadata.get("tcp_ack"))
        if record.get("last_seen") and (not existing.get("last_seen") or record["last_seen"] > existing["last_seen"]):
            existing["last_seen"] = record["last_seen"]
        if record.get("first_seen") and (not existing.get("first_seen") or record["first_seen"] < existing["first_seen"]):
            existing["first_seen"] = record["first_seen"]
    output.extend(aggregated.values())
    return output


def parse_pcap_topology_evidence(
    pcap_path: Path,
    *,
    observer: Optional[str] = None,
    interface: Optional[str] = None,
    include_flows: bool = False,
) -> list[dict[str, Any]]:
    try:
        data = pcap_path.read_bytes()
    except OSError as exc:
        LOG.warning("Could not read passive capture %s: %s", pcap_path, exc)
        return []
    if len(data) < 24:
        return []

    magic = data[:4]
    if magic == b"\xd4\xc3\xb2\xa1":
        endian = "<"
    elif magic == b"\xa1\xb2\xc3\xd4":
        endian = ">"
    else:
        LOG.warning("Skipping unsupported passive capture format in %s", pcap_path)
        return []

    records = []
    offset = 24
    while offset + 16 <= len(data):
        ts_sec, ts_usec, incl_len, orig_len = struct.unpack(endian + "IIII", data[offset : offset + 16])
        offset += 16
        packet = data[offset : offset + incl_len]
        offset += incl_len
        if len(packet) < 14:
            continue
        packet_time = datetime.fromtimestamp(ts_sec + (ts_usec / 1_000_000), timezone.utc).isoformat().replace("+00:00", "Z")
        ether_type = int.from_bytes(packet[12:14], "big")
        payload_offset = 14
        vlan_id = None
        if ether_type == 0x8100 and len(packet) >= 18:
            vlan_id = int.from_bytes(packet[14:16], "big") & 0x0FFF
            ether_type = int.from_bytes(packet[16:18], "big")
            payload_offset = 18
        if ether_type == LLDP_ETHERTYPE:
            parsed = parse_lldp_frame(packet, interface)
            if parsed:
                parsed["observer"] = observer or parsed.get("observer")
                if vlan_id is not None:
                    parsed.setdefault("vlan_id", vlan_id)
                    merge_metadata(parsed, vlan_id=vlan_id)
                records.append(parsed)
            continue
        parsed_cdp = parse_cdp_frame(packet, interface)
        if parsed_cdp:
            parsed_cdp["observer"] = observer or parsed_cdp.get("observer")
            if vlan_id is not None:
                parsed_cdp.setdefault("vlan_id", vlan_id)
                merge_metadata(parsed_cdp, vlan_id=vlan_id)
            records.append(parsed_cdp)
            continue
        payload = packet[payload_offset:]
        if ether_type == LACP_ETHERTYPE:
            parsed_lacp = parse_lacp_evidence(payload, observer=observer, interface=interface, vlan_id=vlan_id)
            if parsed_lacp:
                records.append(parsed_lacp)
            continue
        parsed_stp = parse_stp_evidence(packet, observer=observer, interface=interface, vlan_id=vlan_id)
        if parsed_stp:
            records.append(parsed_stp)
            continue
        if ether_type == 0x0806:
            arp_records = parse_arp_evidence(payload, observer)
            for record in arp_records:
                record["vlan_id"] = vlan_id
                merge_metadata(record, vlan_id=vlan_id)
            records.extend(arp_records)
        elif ether_type in {0x0800, 0x86DD}:
            records.extend(
                parse_ip_packet_evidence(
                    payload,
                    ether_type=ether_type,
                    observer=observer,
                    include_flows=include_flows,
                    vlan_id=vlan_id,
                    captured_len=incl_len,
                    packet_time=packet_time,
                )
            )
    records = aggregate_flow_records(records)
    return canonicalize_entries(
        {key: value for key, value in record.items() if value is not None}
        for record in records
    )


def passive_capture_filter_tokens(include_flows: bool = False) -> list[str]:
    tokens = [
        "(",
        "ether", "proto", "0x88cc",
        "or", "ether", "dst", "01:00:0c:cc:cc:cc",
        "or", "ether", "dst", "01:00:0c:cc:cc:cd",
        "or", "arp",
        "or", "port", "67",
        "or", "port", "68",
        "or", "port", "546",
        "or", "port", "547",
        "or", "port", "53",
        "or", "port", "1900",
        "or", "port", "3702",
        "or", "port", "1985",
        "or", "port", "520",
        "or", "port", "521",
        "or", "port", "179",
        "or", "port", "5353",
        "or", "port", "5355",
        "or", "port", "137",
        "or", "icmp6",
        "or", "ether", "dst", "01:80:c2:00:00:00",
        "or", "ether", "proto", "0x8809",
        "or", "ip", "proto", "88",
        "or", "ip", "proto", "89",
        "or", "ip", "proto", "112",
        ")",
    ]
    if include_flows:
        tokens.extend(["or", "tcp", "or", "udp"])
    return tokens


def default_route_capture_interfaces(
    ignore_filters: Iterable[str] = (),
    timeout_seconds: int = 3,
) -> list[str]:
    command = choose_command(["ip", "-json", "route", "show"])
    if not command:
        LOG.warning("Skipping passive capture interface auto-detection: ip command not found")
        return []

    interfaces = []
    route_commands = [
        command,
        [command[0], "-json", "-6", "route", "show"],
    ]
    for route_command in route_commands:
        try:
            routes = parse_ip_route_json(run_command(route_command, timeout_seconds))
        except (subprocess.SubprocessError, OSError) as exc:
            LOG.debug("Passive capture default route lookup failed for %s: %s", " ".join(route_command), exc)
            continue
        for route in routes:
            interface = route.get("interface")
            if route.get("destination") != "default" or not interface:
                continue
            if is_local_noise_interface(interface):
                continue
            if any(fnmatch(interface, pattern) for pattern in ignore_filters):
                continue
            if interface not in interfaces:
                interfaces.append(interface)
    return interfaces


def passive_capture_options(config: AgentConfig, request_options: Optional[dict[str, Any]]) -> dict[str, Any]:
    requested = request_options or {}
    enabled = bool(requested.get("enabled", config.passive_capture_enabled))
    duration = int(requested.get("duration_seconds", config.passive_capture_duration_seconds) or 60)
    max_bytes = int(requested.get("max_bytes", config.passive_capture_max_bytes) or config.passive_capture_max_bytes)
    interfaces = (
        requested.get("interfaces")
        or config.passive_capture_interfaces
        or default_route_capture_interfaces(config.topology_ignore_filters or [])
    )
    include_flows = bool(requested.get("include_flows", config.passive_capture_include_flows))
    return {
        "enabled": enabled,
        "duration_seconds": min(max(duration, 1), 300),
        "max_bytes": min(max(max_bytes, 65536), 50 * 1024 * 1024),
        "interfaces": interfaces,
        "include_flows": include_flows,
    }


def run_tcpdump_capture(
    interface: str,
    output_path: Path,
    *,
    duration_seconds: int,
    packet_limit: int,
    include_flows: bool,
) -> bool:
    command = choose_command(["tcpdump"])
    if not command:
        LOG.warning("Skipping passive capture: tcpdump command not found")
        return False
    cmd = [
        "tcpdump",
        "-i",
        interface,
        "-s",
        "256",
        "-w",
        str(output_path),
        "-U",
        "-c",
        str(packet_limit),
        *passive_capture_filter_tokens(include_flows),
    ]
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        LOG.warning("Passive capture could not start on %s: %s", interface, exc)
        return False
    try:
        process.wait(timeout=duration_seconds)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
    if process.returncode not in {0, -15}:
        stderr = process.stderr.read() if process.stderr else ""
        LOG.warning("Passive capture on %s exited with %s: %s", interface, process.returncode, stderr.strip())
    return output_path.exists()


def collect_passive_capture_evidence(
    config: AgentConfig,
    request_options: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    options = passive_capture_options(config, request_options)
    if not options["enabled"]:
        return []
    if not options["interfaces"]:
        LOG.warning("Skipping passive capture: no interfaces configured and no default-route interface found")
        return []
    records: list[dict[str, Any]] = []
    for interface in options["interfaces"]:
        if any(fnmatch(interface, pattern) for pattern in config.topology_ignore_filters or []):
            continue
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="grapheon-passive-", suffix=".pcap", delete=False) as handle:
                temp_path = Path(handle.name)
            packet_limit = min(
                config.passive_capture_packet_limit,
                max(1, options["max_bytes"] // 64),
            )
            captured = run_tcpdump_capture(
                interface,
                temp_path,
                duration_seconds=options["duration_seconds"],
                packet_limit=packet_limit,
                include_flows=options["include_flows"],
            )
            if not captured:
                continue
            try:
                if temp_path.stat().st_size > options["max_bytes"]:
                    LOG.warning("Skipping oversized passive capture %s", temp_path)
                    continue
            except OSError:
                continue
            records.extend(
                parse_pcap_topology_evidence(
                    temp_path,
                    observer=socket.gethostname(),
                    interface=interface,
                    include_flows=options["include_flows"],
                )
            )
        finally:
            if temp_path:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass
    return canonicalize_entries(records)


def load_topology_evidence_file(path: Path, max_records: int) -> list[dict[str, Any]]:
    if max_records <= 0:
        return []
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        LOG.warning("Topology evidence file %s could not be read: %s", path, exc)
        return []
    if isinstance(payload, dict):
        records = payload.get("topology_evidence", [])
    else:
        records = payload
    if not isinstance(records, list):
        LOG.warning("Topology evidence file %s did not contain a list", path)
        return []
    bounded = []
    for record in records[:max_records]:
        if isinstance(record, dict):
            bounded.append(record)
    if len(records) > max_records:
        LOG.warning(
            "Topology evidence file %s truncated from %s to %s records",
            path,
            len(records),
            max_records,
        )
    return canonicalize_entries(bounded)


def collect_configured_topology_evidence(
    config: AgentConfig,
    request_options: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_path in config.topology_evidence_paths or []:
        remaining = config.topology_evidence_max_records - len(records)
        if remaining <= 0:
            break
        records.extend(load_topology_evidence_file(Path(raw_path), remaining))
    remaining = config.topology_evidence_max_records - len(records)
    if remaining > 0:
        records.extend(collect_passive_capture_evidence(config, request_options)[:remaining])
    if config.dhcp_lease_paths or config.dns_log_paths or config.zeek_log_dir:
        LOG.info("DHCP/DNS/Zeek paths configured; parser collectors are not implemented by the stdlib agent yet")
    return canonicalize_entries(records)


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
        "metadata": {"runtime": "python-stdlib", "timer_model": "systemd-timer"},
        "addresses": collect_addresses(timeout_seconds, config.ignore_local_net),
    }


def build_current_snapshot(
    policy: dict[str, Any],
    config: AgentConfig,
    ignore_local_net: bool = False,
    passive_capture_request: Optional[dict[str, Any]] = None,
) -> dict[str, list[dict[str, Any]]]:
    timeout_seconds = int(policy.get("command_timeout_seconds", DEFAULT_POLICY["command_timeout_seconds"]))
    commands = policy.get("enabled_commands") or DEFAULT_POLICY["enabled_commands"]
    snapshot = {
        "addresses": collect_addresses(timeout_seconds, ignore_local_net) if commands.get("ip_addr", True) else [],
        "neighbors": collect_neighbors(timeout_seconds, ignore_local_net) if commands.get("ip_neigh", True) else [],
        "connections": collect_connections(timeout_seconds, ignore_local_net) if commands.get("ss_tunap", True) else [],
        "routes": collect_routes(timeout_seconds, ignore_local_net) if commands.get("ip_route", True) else [],
        "topology_evidence": collect_configured_topology_evidence(config, passive_capture_request) if commands.get("topology_evidence", True) else [],
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
    request_headers = {
        "Content-Type": "application/json",
        "User-Agent": config.user_agent,
    }
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


def poll_agent_control(config: AgentConfig, api_key: str, agent_uuid_value: str) -> dict[str, Any]:
    headers = {config.api_key_header: api_key}
    return http_json(
        config,
        "POST",
        "api/agents/poll",
        {"agent_uuid": agent_uuid_value},
        headers=headers,
    )


def is_invalid_agent_api_key_error(exc: RuntimeError) -> bool:
    return (
        "HTTP 401 calling api/agents/poll" in str(exc)
        and "Invalid agent API key" in str(exc)
    )


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

    bypass_jitter = False
    passive_capture_request = None
    if api_key:
        try:
            poll_response = poll_agent_control(config, api_key, agent_uuid_value)
        except RuntimeError as exc:
            if not is_invalid_agent_api_key_error(exc) or not config.enrollment_key:
                raise
            LOG.warning(
                "Stored agent API key was rejected by Graphēon; "
                "clearing local key and falling back to enrollment registration"
            )
            try:
                api_key_path(config).unlink()
            except FileNotFoundError:
                pass
            api_key = None
            registration_response = register_agent(config, agent_uuid_value)
            policy = merged_policy(state, registration_response.get("policy"))
            state["policy"] = policy
            state["agent_id"] = registration_response.get("agent", {}).get("id")
            state["enrollment_state"] = registration_response.get("agent", {}).get("enrollment_state")
            if registration_response.get("status") != "active":
                write_json_file(state_file_path(config), state)
                LOG.info(
                    "Agent %s is %s after API-key recovery registration; waiting for admin approval",
                    agent_uuid_value,
                    registration_response.get("status"),
                )
                return 0
            issued_api_key = registration_response.get("api_key")
            if not issued_api_key:
                raise RuntimeError(
                    "Stored API key was rejected and registration did not return a "
                    "replacement key. Rotate this agent's API key in Graphēon and "
                    "write the new key to the local api_key file."
                ) from exc
            write_text_file(api_key_path(config), issued_api_key)
            api_key = issued_api_key
            LOG.info("Recovered local agent API key through enrollment registration")
            poll_response = {"policy": registration_response.get("policy")}
        policy = merged_policy(state, poll_response.get("policy"))
        state["policy"] = policy
        collection_request = poll_response.get("collection_request") or {}
        if collection_request.get("requested"):
            force = True
            bypass_jitter = True
            passive_capture_request = collection_request.get("passive_capture")
            state["last_collection_request_at"] = collection_request.get("requested_at")
            LOG.info(
                "On-demand collection requested at %s; bypassing local cadence and jitter",
                collection_request.get("requested_at"),
            )

    if not should_run_with_policy(state, policy, config.timer_interval_seconds, force):
        write_json_file(state_file_path(config), state)
        LOG.info("Skipping collection; cached policy interval has not elapsed")
        return 0

    sleep_delay = 0 if bypass_jitter else maybe_sleep_for_policy_jitter(policy)
    state["last_jitter_seconds"] = sleep_delay

    current_snapshot = build_current_snapshot(
        policy,
        config,
        config.ignore_local_net,
        passive_capture_request,
    )
    snapshot_payload, full_snapshot = build_snapshot_payload(
        current_snapshot,
        state.get("last_snapshot") or {},
    )
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
            "snapshot_mode": "full",
        },
        "addresses": snapshot_payload["addresses"],
        "neighbors": snapshot_payload["neighbors"],
        "connections": snapshot_payload["connections"],
        "routes": snapshot_payload["routes"],
        "topology_evidence": snapshot_payload["topology_evidence"],
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
        LOG.info(
            "Starting Graphēon passive agent version %s",
            AGENT_VERSION,
        )
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
