from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Index
from database import Base


class Connection(Base):
    """SQLAlchemy model for network connections (netstat data)."""

    __tablename__ = "connections"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Source host
    local_ip = Column(String(45), nullable=False, index=True)
    local_port = Column(Integer, nullable=False)

    # Destination host
    remote_ip = Column(String(45), nullable=False, index=True)
    remote_port = Column(Integer, nullable=False)

    # Connection info
    protocol = Column(String(10), nullable=False)  # tcp/udp
    state = Column(String(50), nullable=True)  # ESTABLISHED/LISTEN/TIME_WAIT/etc
    pid = Column(Integer, nullable=True)
    process_name = Column(String(255), nullable=True)

    # Metadata
    tags = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)

    # Timestamps
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Data provenance
    source_type = Column(String(50), nullable=True)  # e.g., "netstat", "ss"

    # Indexes
    __table_args__ = (
        Index("idx_connection_local_ip", "local_ip"),
        Index("idx_connection_remote_ip", "remote_ip"),
        Index("idx_connection_protocol", "protocol"),
        Index("idx_connection_state", "state"),
    )

    def __repr__(self):
        return f"<Connection(id={self.id}, {self.local_ip}:{self.local_port} -> {self.remote_ip}:{self.remote_port})>"
