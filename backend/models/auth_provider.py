"""OIDC/OAuth2 provider configuration model."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from database import Base


class AuthProvider(Base):
    """
    Stores configuration for an external OIDC/OAuth2 identity provider.

    Each row represents one provider (e.g. Okta, GitHub, Authentik).
    The frontend fetches enabled providers to render login buttons.
    The backend uses these settings for OIDC discovery and token exchange.
    """

    __tablename__ = "auth_providers"

    id = Column(Integer, primary_key=True, index=True)
    provider_name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    provider_type = Column(
        String(20), nullable=False, default="oidc"
    )  # "oidc" or "oauth2"

    issuer_url = Column(String(500), nullable=False)
    client_id = Column(String(500), nullable=False)
    client_secret = Column(String(500), nullable=False)
    scope = Column(String(1000), nullable=False, default="openid profile email")

    # Cached OIDC discovery endpoints (populated on first use)
    authorization_endpoint = Column(String(500), nullable=True)
    token_endpoint = Column(String(500), nullable=True)
    userinfo_endpoint = Column(String(500), nullable=True)

    display_order = Column(Integer, default=999)
    is_enabled = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationship to role mappings
    role_mappings = relationship(
        "RoleMapping", back_populates="provider", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<AuthProvider {self.provider_name} enabled={self.is_enabled}>"
