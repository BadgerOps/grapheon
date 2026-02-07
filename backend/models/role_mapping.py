"""Maps IdP group claims to application roles."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base


class RoleMapping(Base):
    """
    Maps an IdP claim (typically a group membership) to a Grapheon role.

    Example mappings:
        provider="okta", claim_path="groups", claim_value="net-admins" -> role="admin"
        provider="github", claim_path="orgs", claim_value="BadgerOps"  -> role="editor"

    When a user authenticates, all matching mappings are evaluated.
    The highest-privilege role wins (admin > editor > viewer).
    """

    __tablename__ = "role_mappings"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(
        Integer, ForeignKey("auth_providers.id", ondelete="CASCADE"), nullable=False
    )
    idp_claim_path = Column(String(255), nullable=False)
    idp_claim_value = Column(String(255), nullable=False)
    app_role = Column(String(20), nullable=False)  # admin, editor, viewer
    is_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    provider = relationship("AuthProvider", back_populates="role_mappings")

    __table_args__ = (
        UniqueConstraint(
            "provider_id", "idp_claim_path", "idp_claim_value",
            name="uq_role_mapping_claim",
        ),
    )

    def __repr__(self):
        return (
            f"<RoleMapping {self.idp_claim_path}={self.idp_claim_value} "
            f"-> {self.app_role}>"
        )
