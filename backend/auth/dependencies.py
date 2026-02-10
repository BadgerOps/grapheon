"""
FastAPI dependencies for authentication and role-based access control.

Usage in routers::

    from auth.dependencies import require_role, get_current_user

    @router.get("/admin-only")
    async def admin_endpoint(user: User = Depends(require_admin)):
        ...

    @router.get("/any-authed")
    async def any_endpoint(user: User = Depends(get_current_user)):
        ...
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models.user import User

from .jwt_service import verify_access_token

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract and validate JWT from the ``Authorization: Bearer <token>`` header.

    Returns the authenticated :class:`User`.

    Raises:
        HTTPException 401 if token is missing, invalid, or the user is inactive.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_access_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Like :func:`get_current_user` but returns ``None`` instead of raising
    when authentication is missing or invalid.

    Use this for endpoints that should work both authenticated and
    unauthenticated (e.g. when ``ENFORCE_AUTH=False``).
    """
    if not credentials:
        return None
    try:
        payload = verify_access_token(credentials.credentials)
    except Exception:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    return user


def require_role(*allowed_roles: str):
    """
    Dependency factory for role-based access control.

    Returns a FastAPI dependency that validates the authenticated user
    has one of the specified roles.

    Args:
        *allowed_roles: One or more role strings (``"admin"``, ``"editor"``,
            ``"viewer"``).

    Usage::

        @router.delete("/hosts/{id}")
        async def delete_host(
            host_id: int,
            user: User = Depends(require_role("editor", "admin")),
            db: AsyncSession = Depends(get_db),
        ):
            ...

    Future ABAC: This function could be extended to also check
    resource-level attributes (e.g. subnet ownership) by accepting
    additional parameters and consulting an ABAC policy engine.
    """

    async def _check_role(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        # Demo mode: allow read-only access as a viewer
        if settings.DEMO_MODE:
            # If they have a token, validate it normally
            if credentials:
                try:
                    user = await get_current_user(credentials, db)
                    if user.role in allowed_roles:
                        return user
                except Exception:
                    pass
            # Synthetic viewer — only allowed on viewer-accessible endpoints
            if "viewer" not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Demo mode is read-only. This action requires editor or admin access.",
                )
            return User(
                id=0,
                username="demo-viewer",
                email="demo@localhost",
                display_name="Demo Viewer",
                role="viewer",
                is_active=True,
            )

        # When auth is disabled, allow all requests with a synthetic admin user
        if not settings.AUTH_ENABLED:
            return User(
                id=0,
                username="anonymous",
                email="anon@localhost",
                role="admin",
                is_active=True,
            )

        # When auth is enabled but not enforced, be permissive
        if not settings.ENFORCE_AUTH and not credentials:
            return User(
                id=0,
                username="anonymous",
                email="anon@localhost",
                role="admin",
                is_active=True,
            )

        # Full auth check
        user = await get_current_user(credentials, db)
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient permissions. Your role '{user.role}' "
                    f"does not have access. Required: {', '.join(allowed_roles)}"
                ),
            )
        return user

    return _check_role


# ── Convenience shortcuts ──────────────────────────────────────────────
require_admin = require_role("admin")
require_editor = require_role("editor", "admin")
require_any_authenticated = require_role("viewer", "editor", "admin")
