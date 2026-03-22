from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from database import Base


class AgentCheckIn(Base):
    """Audit record for a passive agent check-in and report ingest."""

    __tablename__ = "agent_checkins"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(
        Integer,
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_import_id = Column(
        Integer,
        ForeignKey("raw_imports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    observed_at = Column(DateTime, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sequence_number = Column(Integer, nullable=True)
    full_snapshot = Column(Boolean, default=False, nullable=False)

    content_encoding = Column(String(50), nullable=True)
    source_ip = Column(String(64), nullable=True)
    auth_method = Column(String(50), nullable=True)
    api_key_prefix = Column(String(32), nullable=True)

    report = Column(JSON, nullable=False)
    summary = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="accepted", index=True)
    error_message = Column(Text, nullable=True)
    records_created = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_agent_checkin_agent_received", "agent_id", "received_at"),
        Index("idx_agent_checkin_status", "status"),
    )

    def __repr__(self):
        return (
            f"<AgentCheckIn(id={self.id}, agent_id={self.agent_id}, "
            f"status={self.status})>"
        )
