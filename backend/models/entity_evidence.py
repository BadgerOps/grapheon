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


class EntityEvidence(Base):
    """Field and relationship evidence attached to canonical entities."""

    __tablename__ = "entity_evidence"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    field_name = Column(String(100), nullable=True, index=True)
    observed_value = Column(Text, nullable=True)

    source_origin = Column(String(50), nullable=False, index=True)
    source_type = Column(String(50), nullable=True, index=True)
    observer_agent_id = Column(
        Integer,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw_import_id = Column(
        Integer,
        ForeignKey("raw_imports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_observation_id = Column(
        Integer,
        ForeignKey("agent_observations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    relationship_type = Column(String(64), nullable=True, index=True)
    confidence = Column(Integer, default=50, nullable=False, index=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_current = Column(Boolean, default=True, nullable=False, index=True)
    evidence_metadata = Column("metadata", JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index("idx_entity_evidence_entity", "entity_type", "entity_id"),
        Index("idx_entity_evidence_field", "entity_type", "entity_id", "field_name"),
        Index("idx_entity_evidence_source", "source_origin", "source_type"),
    )

    def __repr__(self):
        return (
            f"<EntityEvidence(id={self.id}, entity_type={self.entity_type}, "
            f"entity_id={self.entity_id}, field={self.field_name})>"
        )
