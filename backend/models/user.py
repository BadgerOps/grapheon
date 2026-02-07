"""User model for authentication and authorization."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String
from database import Base


class User(Base):
    """
    Application user — created from OIDC login or local admin bootstrap.

    Roles:
        admin   — full access (config, user management, imports, exports, maintenance)
        editor  — can import data, run correlations, manage VLANs, export
        viewer  — read-only access to dashboards, maps, host details, search

    Future ABAC: The ``metadata`` JSON column can store arbitrary attributes
    (department, team, cost_center, etc.) for attribute-based policy evaluation.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    role = Column(String(20), nullable=False, default="viewer", index=True)

    # OIDC identity — set when user logs in via an external IdP
    oidc_subject = Column(String(500), unique=True, nullable=True, index=True)
    oidc_provider = Column(String(100), nullable=True)

    # Local auth — only for bootstrap admin; NULL for OIDC users
    local_password_hash = Column(String(255), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_login_at = Column(DateTime, nullable=True)

    # Future ABAC: flexible attribute storage
    # Example: {"department": "IT", "team": "network-ops", "cost_center": "CC-1234"}
    # Note: named "user_metadata" to avoid conflict with SQLAlchemy's Base.metadata
    user_metadata = Column("user_metadata", JSON, nullable=True)

    def __repr__(self):
        return f"<User {self.username} role={self.role} provider={self.oidc_provider}>"
