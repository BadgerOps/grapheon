from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, JSON, String, Text

from database import Base


DEFAULT_AGENT_COMMANDS = {
    "ip_neigh": True,
    "ss_tunap": True,
    "ip_addr": True,
    "ip_route": True,
}


class AgentPolicy(Base):
    """Low-impact collection profile assigned to one or more agents."""

    __tablename__ = "agent_policies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    checkin_interval_seconds = Column(Integer, nullable=False, default=3600)
    jitter_seconds = Column(Integer, nullable=False, default=300)
    command_timeout_seconds = Column(Integer, nullable=False, default=15)
    enabled_commands = Column(
        JSON,
        nullable=False,
        default=lambda: DEFAULT_AGENT_COMMANDS.copy(),
    )
    max_report_bytes = Column(Integer, nullable=False, default=262144)

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (Index("idx_agent_policy_is_active", "is_active"),)

    def __repr__(self):
        return f"<AgentPolicy(id={self.id}, name={self.name}, active={self.is_active})>"
