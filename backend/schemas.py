"""
Pydantic v2 schemas with strict input validation and lenient output serialization.

Architecture:
  - *Fields classes: pure field definitions, no validators.  Shared by both
    input (Create/Update) and output (Response) schemas.
  - *Create / *Update classes: inherit from *Fields and ADD strict validators
    so bad data is rejected early with clear, actionable error messages.
  - *Response classes: inherit from *Fields directly (no validators) so any
    data already in the database serializes without crashing.

This separation is critical because parsers write directly to DB models and
may produce values that were never validated through the API schemas (e.g.
nmap returns device_type="wireless_ap", netstat returns state="LISTEN").
"""

from datetime import datetime
from typing import Any, Dict, Optional, List
from ipaddress import ip_address as parse_ip
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Allowed value sets (for input validation) ────────────────────────
#
# These cover every value a user should be able to submit via the API.
# They also include values the parsers can produce, so that data round-
# trips cleanly when a user re-submits parser-originated data.

VALID_DEVICE_TYPES = frozenset({
    "router", "switch", "firewall", "server", "workstation",
    "printer", "iot", "phone", "storage", "virtual", "unknown",
    # Additional types produced by nmap _normalize_device_type()
    "wireless_ap", "media", "mobile", "terminal",
    "appliance", "load_balancer", "hub", "bridge", "vpn",
})

VALID_OS_FAMILIES = frozenset({
    "linux", "windows", "macos", "ios", "android",
    "unix", "bsd", "vmware", "unknown",
    # Produced by nmap _infer_os_family() for Cisco/Juniper/etc.
    "network",
})

VALID_CRITICALITIES = frozenset({"critical", "high", "medium", "low"})

VALID_PROTOCOLS = frozenset({"tcp", "udp", "sctp", "ip", "icmp"})

VALID_PORT_STATES = frozenset({
    # Nmap scan states
    "open", "closed", "filtered", "unfiltered",
    "open|filtered", "closed|filtered",
})

VALID_CONNECTION_STATES = frozenset({
    # TCP connection states (netstat / pcap)
    "listen", "established", "time_wait", "close_wait",
    "fin_wait1", "fin_wait2", "syn_recv", "syn_sent",
    "closing", "last_ack", "closed", "unknown",
})

VALID_SOURCE_TYPES = frozenset({
    "nmap", "arp", "netstat", "ping", "traceroute", "pcap", "manual", "agent",
})

VALID_IMPORT_TYPES = frozenset({
    "xml", "grep", "json", "text", "csv", "pcap", "raw",
    "file", "paste", "agent",  # set by the import endpoints themselves
})

VALID_AGENT_COMMANDS = frozenset({
    "ip_neigh",
    "ss_tunap",
    "ip_addr",
    "ip_route",
})

VALID_AGENT_ENROLLMENT_STATES = frozenset({
    "pending",
    "active",
    "rejected",
    "revoked",
})

VALID_AGENT_CHECKIN_STATUSES = frozenset({
    "accepted",
    "rejected",
})

# ── Reusable validators ──────────────────────────────────────────────

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}$")
HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9._\-]+$")

RAW_DATA_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _validate_ip(
    value: str,
    field_name: str = "IP address",
    allow_unspecified: bool = False,
) -> str:
    """Validate an IPv4 or IPv6 address string."""
    try:
        addr = parse_ip(value)
    except ValueError:
        raise ValueError(
            f"Invalid {field_name} '{value}'. "
            "Expected IPv4 (e.g. 192.168.1.1) or IPv6 (e.g. 2001:db8::1)"
        )
    if addr.is_unspecified and not allow_unspecified:
        raise ValueError(
            f"Unspecified {field_name} ({value}) is not allowed"
        )
    return value


def _validate_mac(value: str) -> str:
    """Validate a MAC address string."""
    if not MAC_RE.match(value):
        raise ValueError(
            f"Invalid MAC address '{value}'. "
            "Expected format XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX "
            "(6 pairs of hex digits)"
        )
    return value


def _validate_hostname(value: str) -> str:
    """Validate a hostname string."""
    if len(value) > 255:
        raise ValueError(
            "Hostname too long. Maximum 255 characters allowed"
        )
    if not HOSTNAME_RE.match(value):
        raise ValueError(
            f"Invalid hostname '{value}'. "
            "Use only alphanumeric characters, hyphens, dots, and underscores"
        )
    return value


# ═══════════════════════════════════════════════════════════════════════
# HOST SCHEMAS
# ═══════════════════════════════════════════════════════════════════════

class HostFields(BaseModel):
    """Pure field definitions for hosts.  No validators."""

    ip_address: str
    ip_v6_address: Optional[str] = None
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    fqdn: Optional[str] = None
    netbios_name: Optional[str] = None
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    os_family: Optional[str] = None
    os_confidence: Optional[int] = Field(None, ge=0, le=100)
    device_type: Optional[str] = None
    vendor: Optional[str] = None
    criticality: Optional[str] = None
    owner: Optional[str] = Field(None, max_length=255)
    location: Optional[str] = Field(None, max_length=500)
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)
    is_verified: bool = False
    is_active: bool = True
    source_types: Optional[List[str]] = None


class _HostValidators:
    """Mixin-style validators reused by HostCreate and HostUpdate."""

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, v):
        if v is None:
            return v
        return _validate_ip(v, "IP address")

    @field_validator("ip_v6_address")
    @classmethod
    def validate_ipv6(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            addr = parse_ip(v)
        except ValueError:
            raise ValueError(
                f"Invalid IPv6 address '{v}'. "
                "Expected format like 2001:db8::1"
            )
        if addr.version != 6:
            raise ValueError(
                f"Expected IPv6 address, got IPv4 '{v}'"
            )
        if addr.is_unspecified:
            raise ValueError("Unspecified IPv6 address (::) is not allowed")
        return v

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_mac(v)

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_hostname(v)

    @field_validator("fqdn")
    @classmethod
    def validate_fqdn(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if len(v) > 255:
            raise ValueError("FQDN too long. Maximum 255 characters allowed")
        if not HOSTNAME_RE.match(v):
            raise ValueError(
                f"Invalid FQDN '{v}'. "
                "Use only alphanumeric characters, hyphens, dots, and underscores"
            )
        return v

    @field_validator("os_family")
    @classmethod
    def validate_os_family(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        lower = v.lower()
        if lower not in VALID_OS_FAMILIES:
            raise ValueError(
                f"Invalid OS family '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_OS_FAMILIES))}"
            )
        return lower

    @field_validator("device_type")
    @classmethod
    def validate_device_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        lower = v.lower()
        if lower not in VALID_DEVICE_TYPES:
            raise ValueError(
                f"Invalid device type '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_DEVICE_TYPES))}"
            )
        return lower

    @field_validator("criticality")
    @classmethod
    def validate_criticality(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        lower = v.lower()
        if lower not in VALID_CRITICALITIES:
            raise ValueError(
                f"Invalid criticality '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_CRITICALITIES))}"
            )
        return lower


class HostCreate(HostFields, _HostValidators):
    """Schema for creating a host — fields + strict validation."""
    pass


class HostUpdate(BaseModel, _HostValidators):
    """Schema for updating a host (all fields optional, with validation)."""

    ip_address: Optional[str] = None
    ip_v6_address: Optional[str] = None
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    fqdn: Optional[str] = None
    netbios_name: Optional[str] = None
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    os_family: Optional[str] = None
    os_confidence: Optional[int] = Field(None, ge=0, le=100)
    device_type: Optional[str] = None
    vendor: Optional[str] = None
    criticality: Optional[str] = None
    owner: Optional[str] = Field(None, max_length=255)
    location: Optional[str] = Field(None, max_length=500)
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)
    is_verified: Optional[bool] = None
    is_active: Optional[bool] = None
    source_types: Optional[List[str]] = None


class HostResponse(HostFields):
    """Schema for host responses — no validators, just serialization."""

    id: int
    guid: Optional[str] = None
    device_id: Optional[int] = None
    ports_count: Optional[int] = None
    first_seen: datetime
    last_seen: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Backwards compatibility alias ────────────────────────────────────
HostBase = HostFields


# ═══════════════════════════════════════════════════════════════════════
# PORT SCHEMAS
# ═══════════════════════════════════════════════════════════════════════

class PortFields(BaseModel):
    """Pure field definitions for ports.  No validators."""

    port_number: int = Field(..., ge=0, le=65535)
    protocol: str
    state: str
    service_name: Optional[str] = Field(None, max_length=255)
    service_version: Optional[str] = Field(None, max_length=255)
    service_extrainfo: Optional[str] = Field(None, max_length=1000)
    cpe: Optional[str] = Field(None, max_length=500)
    product: Optional[str] = Field(None, max_length=255)
    version: Optional[str] = Field(None, max_length=255)
    confidence: Optional[int] = Field(None, ge=0, le=10)
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)
    source_types: Optional[List[str]] = None


class _PortValidators:
    """Mixin-style validators reused by PortCreate and PortUpdate."""

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v):
        if v is None:
            return v
        lower = v.lower()
        if lower not in VALID_PROTOCOLS:
            raise ValueError(
                f"Invalid protocol '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_PROTOCOLS))}"
            )
        return lower

    @field_validator("state")
    @classmethod
    def validate_state(cls, v):
        if v is None:
            return v
        lower = v.lower()
        if lower not in VALID_PORT_STATES:
            raise ValueError(
                f"Invalid port state '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_PORT_STATES))}"
            )
        return lower


class PortCreate(PortFields, _PortValidators):
    """Schema for creating a port — fields + strict validation."""
    pass


class PortUpdate(BaseModel, _PortValidators):
    """Schema for updating a port (all fields optional, with validation)."""

    port_number: Optional[int] = Field(None, ge=0, le=65535)
    protocol: Optional[str] = None
    state: Optional[str] = None
    service_name: Optional[str] = Field(None, max_length=255)
    service_version: Optional[str] = Field(None, max_length=255)
    service_extrainfo: Optional[str] = Field(None, max_length=1000)
    cpe: Optional[str] = Field(None, max_length=500)
    product: Optional[str] = Field(None, max_length=255)
    version: Optional[str] = Field(None, max_length=255)
    confidence: Optional[int] = Field(None, ge=0, le=10)
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)
    source_types: Optional[List[str]] = None


class PortResponse(PortFields):
    """Schema for port responses — no validators, just serialization."""

    id: int
    host_id: int
    first_seen: datetime
    last_seen: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Backwards compatibility alias ────────────────────────────────────
PortBase = PortFields


# ═══════════════════════════════════════════════════════════════════════
# CONNECTION SCHEMAS
# ═══════════════════════════════════════════════════════════════════════

class ConnectionFields(BaseModel):
    """Pure field definitions for connections.  No validators."""

    local_ip: str
    local_port: int = Field(..., ge=0, le=65535)
    remote_ip: str
    remote_port: Optional[int] = Field(None, ge=0, le=65535)
    protocol: str
    state: Optional[str] = None
    pid: Optional[int] = None
    process_name: Optional[str] = Field(None, max_length=255)
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)
    source_type: Optional[str] = None


class _ConnectionValidators:
    """Mixin-style validators for ConnectionCreate."""

    @field_validator("local_ip")
    @classmethod
    def validate_local_ip(cls, v):
        if v is None:
            return v
        # Connections allow 0.0.0.0 (LISTEN state binds to all interfaces)
        return _validate_ip(v, "local IP address", allow_unspecified=True)

    @field_validator("remote_ip")
    @classmethod
    def validate_remote_ip(cls, v):
        if v is None:
            return v
        # Connections allow 0.0.0.0 (LISTEN state has no remote peer)
        return _validate_ip(v, "remote IP address", allow_unspecified=True)

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v):
        if v is None:
            return v
        lower = v.lower()
        if lower not in VALID_PROTOCOLS:
            raise ValueError(
                f"Invalid protocol '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_PROTOCOLS))}"
            )
        return lower

    @field_validator("state")
    @classmethod
    def validate_state(cls, v):
        if v is None:
            return v
        lower = v.lower()
        if lower not in VALID_CONNECTION_STATES:
            raise ValueError(
                f"Invalid connection state '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_CONNECTION_STATES))}"
            )
        return lower


class ConnectionCreate(ConnectionFields, _ConnectionValidators):
    """Schema for creating a connection — fields + strict validation."""
    pass


class ConnectionResponse(ConnectionFields):
    """Schema for connection responses — no validators, just serialization."""

    id: int
    first_seen: datetime
    last_seen: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Backwards compatibility alias ────────────────────────────────────
ConnectionBase = ConnectionFields


# ═══════════════════════════════════════════════════════════════════════
# ARP ENTRY SCHEMAS
# ═══════════════════════════════════════════════════════════════════════

class ARPEntryFields(BaseModel):
    """Pure field definitions for ARP entries.  No validators."""

    ip_address: str
    mac_address: str
    interface: Optional[str] = Field(None, max_length=255)
    entry_type: Optional[str] = None
    vendor: Optional[str] = Field(None, max_length=255)
    is_resolved: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)
    source_type: Optional[str] = None


class _ARPValidators:
    """Mixin-style validators for ARPEntryCreate."""

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v):
        if v is None:
            return v
        return _validate_ip(v, "IP address")

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v):
        if v is None:
            return v
        return _validate_mac(v)


class ARPEntryCreate(ARPEntryFields, _ARPValidators):
    """Schema for creating an ARP entry — fields + strict validation."""
    pass


class ARPEntryResponse(ARPEntryFields):
    """Schema for ARP entry responses — no validators, just serialization."""

    id: int
    first_seen: datetime
    last_seen: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Backwards compatibility alias ────────────────────────────────────
ARPEntryBase = ARPEntryFields


# ═══════════════════════════════════════════════════════════════════════
# RAW IMPORT SCHEMAS
# ═══════════════════════════════════════════════════════════════════════

class RawImportFields(BaseModel):
    """Pure field definitions for raw imports.  No validators."""

    source_type: str
    import_type: str
    filename: Optional[str] = Field(None, max_length=500)
    source_host: Optional[str] = None
    raw_data: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)


class _RawImportValidators:
    """Mixin-style validators for RawImportCreate."""

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v):
        if v is None:
            return v
        lower = v.lower()
        if lower not in VALID_SOURCE_TYPES:
            raise ValueError(
                f"Invalid source type '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_SOURCE_TYPES))}"
            )
        return lower

    @field_validator("import_type")
    @classmethod
    def validate_import_type(cls, v):
        if v is None:
            return v
        lower = v.lower()
        if lower not in VALID_IMPORT_TYPES:
            raise ValueError(
                f"Invalid import type '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_IMPORT_TYPES))}"
            )
        return lower

    @field_validator("raw_data")
    @classmethod
    def validate_raw_data(cls, v):
        if v is None:
            return v
        if not v or not v.strip():
            raise ValueError("Raw data cannot be empty")
        if len(v.encode("utf-8", errors="replace")) > RAW_DATA_MAX_BYTES:
            raise ValueError(
                f"Raw data too large. "
                f"Maximum {RAW_DATA_MAX_BYTES // (1024 * 1024)} MB allowed"
            )
        return v

    @field_validator("source_host")
    @classmethod
    def validate_source_host(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # Source host can be an IP or a hostname
        try:
            parse_ip(v)
            return v
        except ValueError:
            pass
        # Allow hostname format
        if not HOSTNAME_RE.match(v) or len(v) > 255:
            raise ValueError(
                f"Invalid source host '{v}'. "
                "Expected a valid IP address or hostname"
            )
        return v


class RawImportCreate(RawImportFields, _RawImportValidators):
    """Schema for creating a raw import — fields + strict validation."""
    pass


class RawImportResponse(RawImportFields):
    """Schema for raw import responses — no validators, just serialization."""

    id: int
    parse_status: str
    parsed_count: int
    error_message: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Backwards compatibility alias ────────────────────────────────────
RawImportBase = RawImportFields


# ═══════════════════════════════════════════════════════════════════════
# DEVICE IDENTITY SCHEMAS
# ═══════════════════════════════════════════════════════════════════════

class DeviceIdentityFields(BaseModel):
    """Pure field definitions for device identities.  No validators."""

    name: Optional[str] = Field(None, max_length=255)
    device_type: Optional[str] = None
    mac_addresses: Optional[List[str]] = None
    ip_addresses: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)
    source: Optional[str] = None
    is_active: bool = True


class _DeviceIdentityValidators:
    """Mixin-style validators for DeviceIdentityCreate/Update."""

    @field_validator("device_type")
    @classmethod
    def validate_device_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        lower = v.lower()
        if lower not in VALID_DEVICE_TYPES:
            raise ValueError(
                f"Invalid device type '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_DEVICE_TYPES))}"
            )
        return lower

    @field_validator("mac_addresses")
    @classmethod
    def validate_mac_list(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        for i, mac in enumerate(v):
            if not MAC_RE.match(mac):
                raise ValueError(
                    f"Invalid MAC address at index {i}: '{mac}'. "
                    "Expected format XX:XX:XX:XX:XX:XX"
                )
        return v

    @field_validator("ip_addresses")
    @classmethod
    def validate_ip_list(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        for i, ip in enumerate(v):
            try:
                parse_ip(ip)
            except ValueError:
                raise ValueError(
                    f"Invalid IP address at index {i}: '{ip}'. "
                    "Expected valid IPv4 or IPv6 address"
                )
        return v


class DeviceIdentityCreate(DeviceIdentityFields, _DeviceIdentityValidators):
    """Schema for creating a device identity — fields + strict validation."""
    pass


class DeviceIdentityUpdate(BaseModel, _DeviceIdentityValidators):
    """Schema for updating a device identity (all fields optional)."""

    name: Optional[str] = Field(None, max_length=255)
    device_type: Optional[str] = None
    mac_addresses: Optional[List[str]] = None
    ip_addresses: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)
    source: Optional[str] = None
    is_active: Optional[bool] = None


class DeviceIdentityResponse(DeviceIdentityFields):
    """Schema for device identity responses — no validators."""

    id: int
    guid: Optional[str] = None
    first_seen: datetime
    last_seen: datetime
    host_count: Optional[int] = None  # Number of linked hosts

    model_config = ConfigDict(from_attributes=True)


# ── Backwards compatibility alias ────────────────────────────────────
DeviceIdentityBase = DeviceIdentityFields


class LinkHostsRequest(BaseModel):
    """Schema for linking hosts to a device identity."""

    host_ids: List[int]


# ═══════════════════════════════════════════════════════════════════════
# AGENT SCHEMAS
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_AGENT_COMMAND_SET = {
    "ip_neigh": True,
    "ss_tunap": True,
    "ip_addr": True,
    "ip_route": True,
}


class AgentPolicyFields(BaseModel):
    """Low-impact passive collection policy distributed to agents."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=4000)
    checkin_interval_seconds: int = Field(3600, ge=60, le=86400)
    jitter_seconds: int = Field(300, ge=0, le=3600)
    command_timeout_seconds: int = Field(15, ge=1, le=300)
    enabled_commands: Dict[str, bool] = Field(
        default_factory=lambda: DEFAULT_AGENT_COMMAND_SET.copy()
    )
    max_report_bytes: int = Field(262144, ge=16384, le=10 * 1024 * 1024)
    is_active: bool = True


class _AgentPolicyValidators:
    @field_validator("enabled_commands")
    @classmethod
    def validate_enabled_commands(cls, value: Dict[str, bool]) -> Dict[str, bool]:
        unexpected = sorted(set(value.keys()) - VALID_AGENT_COMMANDS)
        if unexpected:
            raise ValueError(
                f"Invalid agent commands: {', '.join(unexpected)}. "
                f"Allowed values: {', '.join(sorted(VALID_AGENT_COMMANDS))}"
            )
        return value


class AgentPolicyCreate(AgentPolicyFields, _AgentPolicyValidators):
    """Schema for creating an agent policy."""


class AgentPolicyUpdate(BaseModel, _AgentPolicyValidators):
    """Schema for updating an agent policy."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=4000)
    checkin_interval_seconds: Optional[int] = Field(None, ge=60, le=86400)
    jitter_seconds: Optional[int] = Field(None, ge=0, le=3600)
    command_timeout_seconds: Optional[int] = Field(None, ge=1, le=300)
    enabled_commands: Optional[Dict[str, bool]] = None
    max_report_bytes: Optional[int] = Field(None, ge=16384, le=10 * 1024 * 1024)
    is_active: Optional[bool] = None


class AgentPolicyResponse(AgentPolicyFields):
    """Schema for agent policy responses."""

    id: int
    created_at: datetime
    updated_at: datetime
    agent_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class AgentEnrollmentKeyFields(BaseModel):
    """Admin-managed bootstrap key for enrolling one or more agents."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=4000)
    default_policy_id: Optional[int] = None
    auto_approve: bool = False
    is_active: bool = True
    expires_at: Optional[datetime] = None
    max_registrations: Optional[int] = Field(None, ge=1, le=100000)


class AgentEnrollmentKeyCreate(AgentEnrollmentKeyFields):
    """Schema for creating an enrollment key."""


class AgentEnrollmentKeyUpdate(BaseModel):
    """Schema for updating an enrollment key."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=4000)
    default_policy_id: Optional[int] = None
    auto_approve: Optional[bool] = None
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None
    max_registrations: Optional[int] = Field(None, ge=1, le=100000)


class AgentEnrollmentKeyResponse(AgentEnrollmentKeyFields):
    """Schema for enrollment key responses."""

    id: int
    key_prefix: str
    registration_count: int
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None
    default_policy: Optional[AgentPolicyResponse] = None

    model_config = ConfigDict(from_attributes=True)


class AgentEnrollmentKeyCreateResponse(BaseModel):
    """Schema returned when a new enrollment key is created."""

    enrollment_key: str
    key: AgentEnrollmentKeyResponse


class AgentFields(BaseModel):
    """Registry metadata for a passive agent."""

    agent_uuid: str = Field(..., min_length=1, max_length=128)
    display_name: Optional[str] = Field(None, max_length=255)
    hostname: Optional[str] = Field(None, max_length=255)
    site_name: Optional[str] = Field(None, max_length=255)
    enrollment_key_id: Optional[int] = None
    policy_id: Optional[int] = None
    enrollment_state: str = Field("pending", max_length=20)
    approval_required: bool = True
    agent_version: Optional[str] = Field(None, max_length=100)
    platform: Optional[str] = Field(None, max_length=255)
    platform_release: Optional[str] = Field(None, max_length=255)
    is_active: bool = True


class _AgentValidators:
    @field_validator("enrollment_state")
    @classmethod
    def validate_enrollment_state(cls, value: str) -> str:
        lower = value.lower()
        if lower not in VALID_AGENT_ENROLLMENT_STATES:
            raise ValueError(
                f"Invalid enrollment state '{value}'. "
                f"Allowed values: {', '.join(sorted(VALID_AGENT_ENROLLMENT_STATES))}"
            )
        return lower


class AgentCreate(AgentFields, _AgentValidators):
    """Schema for creating an enrolled agent."""


class AgentUpdate(BaseModel, _AgentValidators):
    """Schema for updating an enrolled agent."""

    display_name: Optional[str] = Field(None, max_length=255)
    hostname: Optional[str] = Field(None, max_length=255)
    site_name: Optional[str] = Field(None, max_length=255)
    enrollment_key_id: Optional[int] = None
    policy_id: Optional[int] = None
    enrollment_state: Optional[str] = Field(None, max_length=20)
    approval_required: Optional[bool] = None
    agent_version: Optional[str] = Field(None, max_length=100)
    platform: Optional[str] = Field(None, max_length=255)
    platform_release: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None


class AgentResponse(AgentFields):
    """Schema for agent registry responses."""

    id: int
    api_key_prefix: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    api_key_issued_at: Optional[datetime] = None
    last_registration_at: Optional[datetime] = None
    last_ip_addresses: Optional[List[str]] = None
    last_mac_addresses: Optional[List[str]] = None
    last_registration_summary: Optional[Dict[str, Any]] = None
    last_checkin_summary: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    last_seen_at: Optional[datetime] = None
    policy: Optional[AgentPolicyResponse] = None
    enrollment_key: Optional[AgentEnrollmentKeyResponse] = None

    model_config = ConfigDict(from_attributes=True)


class AgentNeighborObservation(BaseModel):
    """Single passive neighbor table observation."""

    ip_address: str
    mac_address: Optional[str] = None
    interface: Optional[str] = Field(None, max_length=255)
    state: Optional[str] = Field(None, max_length=50)
    hostname: Optional[str] = Field(None, max_length=255)

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, value: str) -> str:
        return _validate_ip(value, "neighbor IP address")

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_mac(value)


class AgentConnectionObservation(BaseModel):
    """Single passive connection observation."""

    local_ip: str
    local_port: int = Field(..., ge=0, le=65535)
    remote_ip: str
    remote_port: Optional[int] = Field(None, ge=0, le=65535)
    protocol: str
    state: Optional[str] = None
    pid: Optional[int] = None
    process_name: Optional[str] = Field(None, max_length=255)

    @field_validator("local_ip")
    @classmethod
    def validate_local_ip(cls, value: str) -> str:
        return _validate_ip(value, "local IP address", allow_unspecified=True)

    @field_validator("remote_ip")
    @classmethod
    def validate_remote_ip(cls, value: str) -> str:
        return _validate_ip(value, "remote IP address", allow_unspecified=True)

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, value: str) -> str:
        lower = value.lower()
        if lower not in VALID_PROTOCOLS:
            raise ValueError(
                f"Invalid protocol '{value}'. "
                f"Allowed values: {', '.join(sorted(VALID_PROTOCOLS))}"
            )
        return lower

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        lower = value.lower()
        if lower not in VALID_CONNECTION_STATES:
            raise ValueError(
                f"Invalid connection state '{value}'. "
                f"Allowed values: {', '.join(sorted(VALID_CONNECTION_STATES))}"
            )
        return lower


class AgentAddressObservation(BaseModel):
    """Local interface address observation."""

    ip_address: str
    interface: Optional[str] = Field(None, max_length=255)
    prefix_length: Optional[int] = Field(None, ge=0, le=128)
    mac_address: Optional[str] = None

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, value: str) -> str:
        return _validate_ip(value, "interface IP address")

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_mac(value)


class AgentRouteObservation(BaseModel):
    """Local route table observation."""

    destination: str = Field(..., min_length=1, max_length=255)
    gateway: Optional[str] = None
    interface: Optional[str] = Field(None, max_length=255)
    source_ip: Optional[str] = None

    @field_validator("gateway")
    @classmethod
    def validate_gateway(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_ip(value, "route gateway")

    @field_validator("source_ip")
    @classmethod
    def validate_source_ip(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_ip(value, "route source IP")


class AgentRegistrationRequest(BaseModel):
    """Bootstrap request sent by an unenrolled or pending agent."""

    enrollment_key: str = Field(..., min_length=1, max_length=512)
    agent_uuid: str = Field(..., min_length=1, max_length=128)
    display_name: Optional[str] = Field(None, max_length=255)
    hostname: Optional[str] = Field(None, max_length=255)
    site_name: Optional[str] = Field(None, max_length=255)
    agent_version: Optional[str] = Field(None, max_length=100)
    platform: Optional[str] = Field(None, max_length=255)
    platform_release: Optional[str] = Field(None, max_length=255)
    metadata: Optional[Dict[str, Any]] = None
    addresses: List[AgentAddressObservation] = Field(default_factory=list)


class AgentRegistrationResponse(BaseModel):
    """Response returned during enrollment and approval polling."""

    status: str
    approval_required: bool
    message: Optional[str] = None
    api_key: Optional[str] = None
    server_time: datetime
    agent: AgentResponse
    policy: Optional[AgentPolicyResponse] = None


class AgentApprovalRequest(BaseModel):
    """Admin approval or policy assignment for a pending agent."""

    policy_id: Optional[int] = None
    display_name: Optional[str] = Field(None, max_length=255)


class AgentApiKeyRotateRequest(BaseModel):
    """Admin metadata for rotating an agent API key."""

    reason: Optional[str] = Field(None, max_length=1000)


class AgentApiKeyRotateResponse(BaseModel):
    """One-time response returned when an agent API key is rotated."""

    api_key: str
    server_time: datetime
    message: Optional[str] = None
    agent: AgentResponse


class AgentRejectRequest(BaseModel):
    """Admin rejection metadata for a pending agent."""

    reason: Optional[str] = Field(None, max_length=1000)


class AgentCheckInRequest(BaseModel):
    """Normalized passive report uploaded by a deployed agent."""

    agent_uuid: str = Field(..., min_length=1, max_length=128)
    observed_at: datetime
    sequence_number: Optional[int] = Field(None, ge=0)
    full_snapshot: bool = False
    hostname: Optional[str] = Field(None, max_length=255)
    fqdn: Optional[str] = Field(None, max_length=255)
    agent_version: Optional[str] = Field(None, max_length=100)
    platform: Optional[str] = Field(None, max_length=255)
    platform_release: Optional[str] = Field(None, max_length=255)
    metadata: Optional[Dict[str, Any]] = None
    neighbors: List[AgentNeighborObservation] = Field(default_factory=list)
    connections: List[AgentConnectionObservation] = Field(default_factory=list)
    addresses: List[AgentAddressObservation] = Field(default_factory=list)
    routes: List[AgentRouteObservation] = Field(default_factory=list)


class AgentCheckInRecordResponse(BaseModel):
    """Serialized audit record for an agent check-in."""

    id: int
    agent_id: int
    raw_import_id: Optional[int] = None
    observed_at: datetime
    received_at: datetime
    sequence_number: Optional[int] = None
    full_snapshot: bool
    content_encoding: Optional[str] = None
    source_ip: Optional[str] = None
    auth_method: Optional[str] = None
    api_key_prefix: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None
    status: str
    error_message: Optional[str] = None
    records_created: int

    model_config = ConfigDict(from_attributes=True)


class AgentCheckInResponse(BaseModel):
    """Response returned to an agent after a successful check-in."""

    status: str
    server_time: datetime
    agent: AgentResponse
    policy: Optional[AgentPolicyResponse] = None
    checkin: AgentCheckInRecordResponse
    summary: Dict[str, Any]


# ═══════════════════════════════════════════════════════════════════════
# PAGINATION SCHEMAS
# ═══════════════════════════════════════════════════════════════════════

class PaginationParams(BaseModel):
    """Query parameters for pagination."""

    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=1000)


class PaginatedResponse(BaseModel):
    """Generic paginated response."""

    total: int
    skip: int
    limit: int
    items: List
