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
from typing import Optional, List
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
    "nmap", "arp", "netstat", "ping", "traceroute", "pcap", "manual",
})

VALID_IMPORT_TYPES = frozenset({
    "xml", "grep", "json", "text", "csv", "pcap", "raw",
    "file", "paste",  # set by the import endpoints themselves
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
    raw_data: str
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
