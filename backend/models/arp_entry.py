from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Index
from database import Base


class ARPEntry(Base):
    """SQLAlchemy model for ARP (Address Resolution Protocol) entries."""

    __tablename__ = "arp_entries"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # ARP information
    ip_address = Column(String(45), nullable=False, index=True)
    mac_address = Column(String(17), nullable=False, index=True)
    interface = Column(String(50), nullable=True)
    entry_type = Column(String(50), nullable=True)  # dynamic/static/failed/permanent
    vendor = Column(String(255), nullable=True)

    # Resolution status
    is_resolved = Column(String(50), nullable=True)  # complete/incomplete/permanent/etc

    # Metadata
    tags = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)

    # Timestamps
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Data provenance
    source_type = Column(String(50), nullable=True)  # e.g., "arp_scan", "arp_table"

    # Indexes
    __table_args__ = (
        Index("idx_arp_ip_address", "ip_address"),
        Index("idx_arp_mac_address", "mac_address"),
        Index("idx_arp_ip_mac", "ip_address", "mac_address"),
    )

    def __repr__(self):
        return f"<ARPEntry(id={self.id}, ip={self.ip_address}, mac={self.mac_address})>"
