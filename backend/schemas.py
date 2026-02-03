from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# Host schemas
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
    os_confidence: Optional[int] = None
    device_type: Optional[str] = None
    vendor: Optional[str] = None
    criticality: Optional[str] = None
    owner: Optional[str] = None
    location: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    is_verified: bool = False
    is_active: bool = True
    source_types: Optional[List[str]] = None


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
    os_confidence: Optional[int] = None
    device_type: Optional[str] = None
    vendor: Optional[str] = None
    criticality: Optional[str] = None
    owner: Optional[str] = None
    location: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    is_verified: Optional[bool] = None
    is_active: Optional[bool] = None
    source_types: Optional[List[str]] = None


class HostResponse(HostBase):
    """Schema for host response."""

    id: int
    guid: Optional[str] = None
    ports_count: Optional[int] = None
    first_seen: datetime
    last_seen: datetime

    class Config:
        from_attributes = True


# Port schemas
class PortBase(BaseModel):
    """Base schema for port creation/update."""

    port_number: int
    protocol: str
    state: str
    service_name: Optional[str] = None
    service_version: Optional[str] = None
    service_extrainfo: Optional[str] = None
    cpe: Optional[str] = None
    product: Optional[str] = None
    version: Optional[str] = None
    confidence: Optional[int] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    source_types: Optional[List[str]] = None


class PortCreate(PortBase):
    """Schema for creating a port."""

    pass


class PortUpdate(BaseModel):
    """Schema for updating a port."""

    port_number: Optional[int] = None
    protocol: Optional[str] = None
    state: Optional[str] = None
    service_name: Optional[str] = None
    service_version: Optional[str] = None
    service_extrainfo: Optional[str] = None
    cpe: Optional[str] = None
    product: Optional[str] = None
    version: Optional[str] = None
    confidence: Optional[int] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    source_types: Optional[List[str]] = None


class PortResponse(PortBase):
    """Schema for port response."""

    id: int
    host_id: int
    first_seen: datetime
    last_seen: datetime

    class Config:
        from_attributes = True


# Connection schemas
class ConnectionBase(BaseModel):
    """Base schema for connection."""

    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    protocol: str
    state: Optional[str] = None
    pid: Optional[int] = None
    process_name: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    source_type: Optional[str] = None


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


# ARP Entry schemas
class ARPEntryBase(BaseModel):
    """Base schema for ARP entry."""

    ip_address: str
    mac_address: str
    interface: Optional[str] = None
    entry_type: Optional[str] = None
    vendor: Optional[str] = None
    is_resolved: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    source_type: Optional[str] = None


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


# Raw import schemas
class RawImportBase(BaseModel):
    """Base schema for raw import."""

    source_type: str
    import_type: str
    filename: Optional[str] = None
    source_host: Optional[str] = None
    raw_data: str
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


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


# Pagination schemas
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
