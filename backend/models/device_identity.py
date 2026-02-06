"""
Device Identity model for tracking multi-homed physical devices.

A DeviceIdentity represents a single physical device (e.g., a router)
that may have multiple IP addresses across different subnets/VLANs.
Instead of merging these host records (which would lose per-subnet identity),
we link them via device_id to indicate they're the same physical box.

Key use cases:
- Multi-homed routers with IPs on multiple subnets
- Firewalls with inside/outside/DMZ interfaces
- Servers with management + data interfaces
"""

from datetime import datetime
import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, Index

from database import Base


class DeviceIdentity(Base):
    """SQLAlchemy model for physical device identity."""

    __tablename__ = "device_identities"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    guid = Column(
        String(36),
        unique=True,
        index=True,
        nullable=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Device info
    name = Column(String(255), nullable=True)  # User-friendly name, e.g. "Core Router 01"
    device_type = Column(String(50), nullable=True)  # router/switch/firewall/server/etc
    mac_addresses = Column(JSON, nullable=True)  # List of known MACs on this device
    ip_addresses = Column(JSON, nullable=True)  # List of known IPs on this device

    # Metadata
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    # How this identity was created
    source = Column(
        String(50), nullable=True
    )  # "mac_correlation", "manual", "lldp", etc

    # Timestamps
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (Index("idx_device_identity_is_active", "is_active"),)

    def __repr__(self):
        return (
            f"<DeviceIdentity(id={self.id}, name={self.name}, "
            f"device_type={self.device_type}, ips={self.ip_addresses})>"
        )
