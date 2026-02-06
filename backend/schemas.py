"""
Pydantic v2 schemas with strict field validation.

Every network-relevant field (IP, MAC, port, protocol, device_type, etc.)
is validated at the schema boundary so bad data is rejected early with
clear, actionable error messages.
"""

from datetime import datetime
from typing import Optional, List
from ipaddress import ip_address as parse_ip
import re

from pydantic import BaseModel, Field, field_validator


# ── Allowed value sets ────────────────────────────────────────────────

VALID_DEVICE_TYPES = frozenset({
    "router", "switch", "firewall", "server", "workstation",
    "printer", "iot", "phone", "storage", "virtual", "unknown",
})

VALID_OS_FAMILIES = frozenset({
    "linux", "windows", "macos", "ios", "android",
    "unix", "bsd", "vmware", "unknown",
})

VALID_CRITICALITIES = frozenset({"critical", "high", "medium", "low"})

VALID_PROTOCOLS = frozenset({"tcp", "udp", "sctp", "ip"})

VALID_PORT_STATES = frozenset({"open", "closed", "filtered", "unfiltered"})

VALID_SOURCE_TYPES = frozenset({
    "nmap", "arp", "netstat", "ping", "traceroute", "pcap", "manual",
})

VALID_IMPORT_TYPES = frozenset({
    "xml", "grep", "json", "text", "csv", "pcap", "raw",
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


# ── Host schemas ──────────────────────────────────────────────────────

class HostBase(BaseModel):
    """Base schema for host creation/update."""

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

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, v: str) -> str:
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


class HostCreate(HostBase):
    """Schema for creating a host."""

    pass


class HostUpdate(BaseModel):
    """Schema for updating a host (all fields optional)."""

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

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, v: Optional[str]) -> Optional[str]:
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
            raise ValueError(f"Expected IPv6 address, got IPv4 '{v}'")
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


class HostResponse(HostBase):
    """Schema for host response."""

    id: int
    guid: Optional[str] = None
    device_id: Optional[int] = None
    ports_count: Optional[int] = None
    first_seen: datetime
    last_seen: datetime

    class Config:
        from_attributes = True


# ── Port schemas ──────────────────────────────────────────────────────

class PortBase(BaseModel):
    """Base schema for port creation/update."""

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

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        lower = v.lower()
        if lower not in VALID_PROTOCOLS:
            raise ValueError(
                f"Invalid protocol '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_PROTOCOLS))}"
            )
        return lower

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        lower = v.lower()
        if lower not in VALID_PORT_STATES:
            raise ValueError(
                f"Invalid port state '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_PORT_STATES))}"
            )
        return lower


class PortCreate(PortBase):
    """Schema for creating a port."""

    pass


class PortUpdate(BaseModel):
    """Schema for updating a port."""

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

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v: Optional[str]) -> Optional[str]:
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
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        lower = v.lower()
        if lower not in VALID_PORT_STATES:
            raise ValueError(
                f"Invalid port state '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_PORT_STATES))}"
            )
        return lower


class PortResponse(PortBase):
    """Schema for port response."""

    id: int
    host_id: int
    first_seen: datetime
    last_seen: datetime

    class Config:
        from_attributes = True


# ── Connection schemas ────────────────────────────────────────────────

class ConnectionBase(BaseModel):
    """Base schema for connection."""

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

    @field_validator("local_ip")
    @classmethod
    def validate_local_ip(cls, v: str) -> str:
        # Connections allow 0.0.0.0 (LISTEN state binds to all interfaces)
        return _validate_ip(v, "local IP address", allow_unspecified=True)

    @field_validator("remote_ip")
    @classmethod
    def validate_remote_ip(cls, v: str) -> str:
        # Connections allow 0.0.0.0 (LISTEN state has no remote peer)
        return _validate_ip(v, "remote IP address", allow_unspecified=True)

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        lower = v.lower()
        if lower not in VALID_PROTOCOLS:
            raise ValueError(
                f"Invalid protocol '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_PROTOCOLS))}"
            )
        return lower


class ConnectionCreate(ConnectionBase):
    """Schema for creating a connection."""

    pass


class ConnectionResponse(ConnectionBase):
    """Schema for connection response."""

    id: int
    first_seen: datetime
    last_seen: datetime

    class Config:
        from_attributes = True


# ── ARP Entry schemas ─────────────────────────────────────────────────

class ARPEntryBase(BaseModel):
    """Base schema for ARP entry."""

    ip_address: str
    mac_address: str
    interface: Optional[str] = Field(None, max_length=255)
    entry_type: Optional[str] = None
    vendor: Optional[str] = Field(None, max_length=255)
    is_resolved: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)
    source_type: Optional[str] = None

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        return _validate_ip(v, "IP address")

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        return _validate_mac(v)


class ARPEntryCreate(ARPEntryBase):
    """Schema for creating an ARP entry."""

    pass


class ARPEntryResponse(ARPEntryBase):
    """Schema for ARP entry response."""

    id: int
    first_seen: datetime
    last_seen: datetime

    class Config:
        from_attributes = True


# ── Raw import schemas ────────────────────────────────────────────────

class RawImportBase(BaseModel):
    """Base schema for raw import."""

    source_type: str
    import_type: str
    filename: Optional[str] = Field(None, max_length=500)
    source_host: Optional[str] = None
    raw_data: str
    tags: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        lower = v.lower()
        if lower not in VALID_SOURCE_TYPES:
            raise ValueError(
                f"Invalid source type '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_SOURCE_TYPES))}"
            )
        return lower

    @field_validator("import_type")
    @classmethod
    def validate_import_type(cls, v: str) -> str:
        lower = v.lower()
        if lower not in VALID_IMPORT_TYPES:
            raise ValueError(
                f"Invalid import type '{v}'. "
                f"Allowed values: {', '.join(sorted(VALID_IMPORT_TYPES))}"
            )
        return lower

    @field_validator("raw_data")
    @classmethod
    def validate_raw_data(cls, v: str) -> str:
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


class RawImportCreate(RawImportBase):
    """Schema for creating a raw import."""

    pass


class RawImportResponse(RawImportBase):
    """Schema for raw import response."""

    id: int
    parse_status: str
    parsed_count: int
    error_message: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Device Identity schemas ───────────────────────────────────────────

class DeviceIdentityBase(BaseModel):
    """Base schema for device identity."""

    name: Optional[str] = Field(None, max_length=255)
    device_type: Optional[str] = None
    mac_addresses: Optional[List[str]] = None
    ip_addresses: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)
    source: Optional[str] = None
    is_active: bool = True

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


class DeviceIdentityCreate(DeviceIdentityBase):
    """Schema for creating a device identity."""

    pass


class DeviceIdentityUpdate(BaseModel):
    """Schema for updating a device identity (all fields optional)."""

    name: Optional[str] = Field(None, max_length=255)
    device_type: Optional[str] = None
    mac_addresses: Optional[List[str]] = None
    ip_addresses: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=5000)
    source: Optional[str] = None
    is_active: Optional[bool] = None

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


class DeviceIdentityResponse(DeviceIdentityBase):
    """Schema for device identity response."""

    id: int
    guid: Optional[str] = None
    first_seen: datetime
    last_seen: datetime
    host_count: Optional[int] = None  # Number of linked hosts

    class Config:
        from_attributes = True


class LinkHostsRequest(BaseModel):
    """Schema for linking hosts to a device identity."""

    host_ids: List[int]


# ── Pagination schemas ────────────────────────────────────────────────

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
