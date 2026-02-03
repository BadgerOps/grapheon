from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Index
from database import Base


class Port(Base):
    """SQLAlchemy model for network ports on hosts."""

    __tablename__ = "ports"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign key to host
    host_id = Column(Integer, ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)

    # Port information
    port_number = Column(Integer, nullable=False)
    protocol = Column(String(10), nullable=False)  # tcp/udp
    state = Column(String(50), nullable=False)  # open/closed/filtered/open|filtered

    # Service information
    service_name = Column(String(255), nullable=True)
    service_version = Column(String(255), nullable=True)
    service_extrainfo = Column(String(255), nullable=True)

    # Security data
    cpe = Column(String(255), nullable=True)  # Common Platform Enumeration
    product = Column(String(255), nullable=True)
    version = Column(String(255), nullable=True)
    confidence = Column(Integer, nullable=True)  # 0-100

    # Metadata
    tags = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)

    # Timestamps
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Data provenance
    source_types = Column(JSON, nullable=True)  # e.g., ["nmap", "netstat"]

    # Indexes
    __table_args__ = (
        Index("idx_port_host_id", "host_id"),
        Index("idx_port_port_number", "port_number"),
        Index("idx_port_protocol", "protocol"),
        Index("idx_port_state", "state"),
    )

    def __repr__(self):
        return f"<Port(id={self.id}, host_id={self.host_id}, port={self.port_number}/{self.protocol}, state={self.state})>"
