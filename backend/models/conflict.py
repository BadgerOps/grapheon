from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Index, Boolean
from database import Base


class Conflict(Base):
    """SQLAlchemy model for tracking data conflicts in correlated hosts."""

    __tablename__ = "conflicts"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign key to host
    host_id = Column(Integer, ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)

    # Conflict information
    conflict_type = Column(
        String(50), nullable=False
    )  # mac_mismatch, os_mismatch, hostname_mismatch, etc
    field = Column(String(100), nullable=False)  # which field has the conflict

    # Conflicting values with their sources
    values = Column(JSON, nullable=False)  # [{"value": "...", "source": "...", "timestamp": "..."}]

    # Resolution tracking
    resolved = Column(Boolean, default=False, index=True)
    resolution = Column(Text, nullable=True)  # How it was resolved
    resolved_by = Column(String(255), nullable=True)  # Who resolved it
    resolved_at = Column(DateTime, nullable=True)

    # Timestamps
    detected_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Indexes
    __table_args__ = (
        Index("idx_conflict_host_id", "host_id"),
        Index("idx_conflict_type", "conflict_type"),
        Index("idx_conflict_resolved", "resolved"),
        Index("idx_conflict_detected_at", "detected_at"),
    )

    def __repr__(self):
        return f"<Conflict(id={self.id}, host_id={self.host_id}, type={self.conflict_type}, field={self.field})>"
