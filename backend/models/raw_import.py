from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from database import Base


class RawImport(Base):
    """SQLAlchemy model for raw import audit log."""

    __tablename__ = "raw_imports"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Import metadata
    source_type = Column(String(100), nullable=False)  # e.g., "nmap", "netstat", "arp_scan"
    import_type = Column(String(50), nullable=False)  # "paste" or "file"
    filename = Column(String(255), nullable=True)
    source_host = Column(String(255), nullable=True)

    # Raw data
    raw_data = Column(Text, nullable=False)

    # Parse results
    parse_status = Column(String(50), default="pending")  # pending/success/failed/partial
    parsed_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # Parse results metadata
    parse_results = Column(JSON, nullable=True)  # Store structured parse results

    # Metadata
    tags = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<RawImport(id={self.id}, source_type={self.source_type}, status={self.parse_status})>"
