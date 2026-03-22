from datetime import datetime
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)

from database import Base


class Agent(Base):
    """Enrolled passive agent managed by the Graphēon backend."""

    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    agent_uuid = Column(String(128), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    hostname = Column(String(255), nullable=True)
    site_name = Column(String(255), nullable=True)

    enrollment_key_id = Column(
        Integer,
        ForeignKey("agent_enrollment_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    policy_id = Column(
        Integer,
        ForeignKey("agent_policies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    enrollment_state = Column(String(20), nullable=False, default="pending", index=True)
    approval_required = Column(Boolean, default=True, nullable=False)
    legacy_mtls_identity = Column(
        "mtls_identity",
        String(500),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: f"legacy:{uuid.uuid4()}",
    )
    api_key_hash = Column(String(64), unique=True, nullable=True, index=True)
    api_key_prefix = Column(String(32), nullable=True, index=True)

    agent_version = Column(String(100), nullable=True)
    platform = Column(String(255), nullable=True)
    platform_release = Column(String(255), nullable=True)

    approved_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    api_key_issued_at = Column(DateTime, nullable=True)
    last_registration_at = Column(DateTime, nullable=True)
    last_ip_addresses = Column(JSON, nullable=True)
    last_mac_addresses = Column(JSON, nullable=True)
    last_registration_summary = Column(JSON, nullable=True)
    last_checkin_summary = Column(JSON, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    last_seen_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_agent_enrollment_key_id", "enrollment_key_id"),
        Index("idx_agent_policy_id", "policy_id"),
        Index("idx_agent_last_seen_at", "last_seen_at"),
    )

    def __repr__(self):
        return (
            f"<Agent(id={self.id}, agent_uuid={self.agent_uuid}, "
            f"state={self.enrollment_state})>"
        )
