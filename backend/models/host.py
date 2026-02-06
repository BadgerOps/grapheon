from datetime import datetime
import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, Index
from database import Base


class Host(Base):
    """SQLAlchemy model for network hosts."""

    __tablename__ = "hosts"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    guid = Column(String(36), unique=True, index=True, nullable=True, default=lambda: str(uuid.uuid4()))

    # IP addresses
    ip_address = Column(String(45), nullable=False, index=True)
    ip_v6_address = Column(String(45), nullable=True)

    # MAC and network info
    mac_address = Column(String(17), nullable=True, index=True)
    hostname = Column(String(255), nullable=True)
    fqdn = Column(String(255), nullable=True)
    netbios_name = Column(String(255), nullable=True)

    # Operating system
    os_name = Column(String(255), nullable=True)
    os_version = Column(String(255), nullable=True)
    os_family = Column(String(50), nullable=True)  # linux/windows/macos/network/unknown
    os_confidence = Column(Integer, nullable=True)  # 0-100

    # Device classification
    device_type = Column(
        String(50), nullable=True
    )  # server/workstation/router/printer/iot/unknown
    vendor = Column(String(255), nullable=True)

    # VLAN assignment
    vlan_id = Column(Integer, nullable=True, index=True)  # 802.1Q VLAN ID (0-4094)
    vlan_name = Column(String(32), nullable=True)  # e.g., "DMZ", "Internal", "Guest"
    criticality = Column(String(20), nullable=True)  # low/medium/high/critical
    owner = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)

    # Metadata
    tags = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Timestamps
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Data provenance
    source_types = Column(JSON, nullable=True)  # e.g., ["nmap", "arp", "netstat"]

    # Indexes
    __table_args__ = (
        Index("idx_host_ip_address", "ip_address"),
        Index("idx_host_mac_address", "mac_address"),
        Index("idx_host_is_active", "is_active"),
    )

    def __repr__(self):
        return f"<Host(id={self.id}, ip_address={self.ip_address}, hostname={self.hostname})>"
