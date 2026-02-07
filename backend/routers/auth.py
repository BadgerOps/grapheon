"""
Authentication and user management endpoints.

Public endpoints:
    GET  /api/auth/providers          — list enabled OIDC providers
    POST /api/auth/callback           — exchange OIDC code for JWT
    POST /api/auth/login/local        — local admin username/password login

Protected endpoints:
    GET  /api/auth/me                 — current user info
    POST /api/auth/logout             — audit-only logout
    GET  /api/auth/users              — list all users (admin)
    PATCH /api/auth/users/{id}/role   — change user role (admin)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import bcrypt as _bcrypt

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import User, AuthProvider
from auth.jwt_service import create_access_token
from auth import oidc_service
from auth.dependencies import get_current_user, require_admin
from utils.audit import audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return _bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ── Schemas ────────────────────────────────────────────────────────────


class ProviderInfo(BaseModel):
    name: str
    display_name: str
    provider_type: str
    authorization_endpoint: Optional[str] = None
    client_id: Optional[str] = None
    scope: Optional[str] = None


class ProviderListResponse(BaseModel):
    providers: list[ProviderInfo]
    local_auth_enabled: bool


class OIDCCallbackRequest(BaseModel):
    code: str
    provider: str
    redirect_uri: str
    code_verifier: Optional[str] = None


class LocalLoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user_id: int
    username: str
    email: str
    role: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    display_name: Optional[str] = None
    role: str
    oidc_provider: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RoleUpdateRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|editor|viewer)$")


# ── Public endpoints ───────────────────────────────────────────────────


@router.get("/providers", response_model=ProviderListResponse)
async def list_providers(db: AsyncSession = Depends(get_db)):
    """List enabled OIDC providers and whether local auth is available."""
    result = await db.execute(
        select(AuthProvider)
        .where(AuthProvider.is_enabled.is_(True))
        .order_by(AuthProvider.display_order)
    )
    providers = result.scalars().all()

    provider_list = []
    for p in providers:
        # If authorization_endpoint is not cached, try discovery
        auth_endpoint = p.authorization_endpoint
        if not auth_endpoint and p.issuer_url:
            try:
                endpoints = await oidc_service.discover_endpoints(p.issuer_url)
                auth_endpoint = endpoints.get("authorization_endpoint")
            except Exception:
                logger.warning(
                    f"OIDC discovery failed for {p.provider_name}", exc_info=True
                )

        provider_list.append(
            ProviderInfo(
                name=p.provider_name,
                display_name=p.display_name,
                provider_type=p.provider_type,
                authorization_endpoint=auth_endpoint,
                client_id=p.client_id,
                scope=p.scope,
            )
        )

    # Check if any local admin exists
    local_result = await db.execute(
        select(func.count())
        .select_from(User)
        .where(User.local_password_hash.isnot(None))
    )
    has_local_users = local_result.scalar() > 0

    return ProviderListResponse(
        providers=provider_list,
        local_auth_enabled=settings.ENABLE_LOCAL_AUTH if hasattr(settings, "ENABLE_LOCAL_AUTH") else has_local_users,
    )


@router.post("/callback", response_model=TokenResponse)
async def oidc_callback(
    request: OIDCCallbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Complete OIDC login: exchange authorization code for tokens,
    create/update user, return a signed JWT.
    """
    # Find provider
    result = await db.execute(
        select(AuthProvider).where(
            AuthProvider.provider_name == request.provider,
            AuthProvider.is_enabled.is_(True),
        )
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{request.provider}' not found or disabled",
        )

    # Exchange code for tokens
    try:
        token_response = await oidc_service.exchange_code(
            provider=provider,
            code=request.code,
            redirect_uri=request.redirect_uri,
            code_verifier=request.code_verifier,
        )
    except Exception as exc:
        logger.error(f"Token exchange failed for {request.provider}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token exchange failed",
        )

    # Get user info (prefer ID token claims, fall back to userinfo endpoint)
    access_token = token_response.get("access_token", "")
    try:
        claims = await oidc_service.fetch_userinfo(provider, access_token)
    except Exception as exc:
        logger.error(f"Userinfo fetch failed for {request.provider}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fetch user information",
        )

    # Extract identity fields
    sub = claims.get("sub", "")
    email = claims.get("email", f"{sub}@{request.provider}")
    name = claims.get("name") or claims.get("preferred_username") or email.split("@")[0]
    username = (
        claims.get("preferred_username")
        or email.split("@")[0]
        or sub[:50]
    )

    # Resolve role from claims
    role = await oidc_service.resolve_role(db, provider, claims)

    # Get or create user
    result = await db.execute(
        select(User).where(User.oidc_subject == sub, User.oidc_provider == request.provider)
    )
    user = result.scalar_one_or_none()

    if user:
        user.last_login_at = datetime.now(timezone.utc)
        user.role = role
        user.email = email
        user.display_name = name
    else:
        # Ensure username is unique
        existing = await db.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none():
            username = f"{username}_{sub[:8]}"

        user = User(
            username=username,
            email=email,
            display_name=name,
            role=role,
            oidc_subject=sub,
            oidc_provider=request.provider,
            is_active=True,
            last_login_at=datetime.now(timezone.utc),
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)

    # Create JWT
    jwt_token = create_access_token(user_id=user.id, role=user.role)

    audit.log(
        action="LOGIN",
        actor=user.username,
        resource="User",
        resource_id=str(user.id),
        status="success",
        details={"provider": request.provider, "method": "oidc"},
    )

    return TokenResponse(
        access_token=jwt_token,
        expires_in=settings.JWT_EXPIRATION_MINUTES * 60,
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
    )


@router.post("/login/local", response_model=TokenResponse)
async def local_login(
    request: LocalLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with local username/password (for bootstrap admin)."""
    result = await db.execute(
        select(User).where(
            User.username == request.username,
            User.local_password_hash.isnot(None),
        )
    )
    user = result.scalar_one_or_none()

    if not user or not _verify_password(request.password, user.local_password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    jwt_token = create_access_token(user_id=user.id, role=user.role)

    audit.log(
        action="LOGIN",
        actor=user.username,
        resource="User",
        resource_id=str(user.id),
        status="success",
        details={"method": "local"},
    )

    return TokenResponse(
        access_token=jwt_token,
        expires_in=settings.JWT_EXPIRATION_MINUTES * 60,
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
    )


# ── Protected endpoints ────────────────────────────────────────────────


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Get the authenticated user's profile."""
    return UserResponse.model_validate(user)


@router.post("/logout")
async def logout(user: User = Depends(get_current_user)):
    """
    Logout endpoint — records the event in audit log.

    Note: JWTs are stateless and cannot be invalidated server-side without
    a token blacklist. The frontend should discard the token on logout.
    A Redis-backed blacklist can be added for stricter invalidation.
    """
    audit.log(
        action="LOGOUT",
        actor=user.username,
        resource="User",
        resource_id=str(user.id),
        status="success",
    )
    return {"status": "ok", "message": "Logged out"}


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin only)."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return [UserResponse.model_validate(u) for u in result.scalars().all()]


@router.patch("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: int,
    body: RoleUpdateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Change a user's role (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = target_user.role
    target_user.role = body.role
    await db.commit()
    await db.refresh(target_user)

    audit.log(
        action="UPDATE_ROLE",
        actor=current_user.username,
        resource="User",
        resource_id=str(target_user.id),
        status="success",
        details={"old_role": old_role, "new_role": body.role},
    )

    return UserResponse.model_validate(target_user)
