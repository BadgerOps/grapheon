from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, JSON, String, Text

from database import Base


class NetworkGroup(Base):
    """Operator-defined network grouping hint for topology views."""

    __tablename__ = "network_groups"

    id = Column(Integer, primary_key=True, index=True)
    cidr = Column(String(64), unique=True, nullable=False, index=True)
    label = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    source = Column(String(50), default="manual", nullable=False, index=True)
    confidence = Column(Integer, default=100, nullable=False)
    is_expected = Column(Boolean, default=True, nullable=False, index=True)
    is_hidden = Column(Boolean, default=False, nullable=False, index=True)
    group_metadata = Column("metadata", JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index("idx_network_groups_cidr", "cidr"),
        Index("idx_network_groups_source", "source"),
        Index("idx_network_groups_expected", "is_expected"),
        Index("idx_network_groups_hidden", "is_hidden"),
    )

    def __repr__(self):
        return f"<NetworkGroup(cidr={self.cidr}, label={self.label})>"
