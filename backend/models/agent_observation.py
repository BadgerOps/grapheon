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
    UniqueConstraint,
)

from database import Base


class AgentObservation(Base):
    """Agent-scoped full-snapshot observation state."""

    __tablename__ = "agent_observations"

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
    last_seen_checkin_id = Column(
        Integer,
        ForeignKey("agent_checkins.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    observation_type = Column(String(32), nullable=False, index=True)
    identity_hash = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, nullable=False)

    host_id = Column(
        Integer,
        ForeignKey("hosts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    arp_entry_id = Column(
        Integer,
        ForeignKey("arp_entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    connection_id = Column(
        Integer,
        ForeignKey("connections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    stale_at = Column(DateTime, nullable=True)
    removed_at = Column(DateTime, nullable=True)
    is_current = Column(Boolean, default=True, nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "agent_id",
            "observation_type",
            "identity_hash",
            name="uq_agent_observation_identity",
        ),
        Index("idx_agent_observation_agent_type", "agent_id", "observation_type"),
        Index("idx_agent_observation_current", "agent_id", "is_current"),
    )

    def __repr__(self):
        return (
            f"<AgentObservation(id={self.id}, agent_id={self.agent_id}, "
            f"type={self.observation_type}, current={self.is_current})>"
        )
