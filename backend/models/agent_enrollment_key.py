from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from database import Base


class AgentEnrollmentKey(Base):
    """Admin-created shared enrollment credential for bootstrapping agents."""

    __tablename__ = "agent_enrollment_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    key_prefix = Column(String(32), nullable=False, index=True)

    default_policy_id = Column(
        Integer,
        ForeignKey("agent_policies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    auto_approve = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=True)
    max_registrations = Column(Integer, nullable=True)
    registration_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    last_used_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_agent_enrollment_key_is_active", "is_active"),
        Index("idx_agent_enrollment_key_default_policy_id", "default_policy_id"),
    )

    def __repr__(self):
        return (
            f"<AgentEnrollmentKey(id={self.id}, name={self.name}, "
            f"active={self.is_active})>"
        )
