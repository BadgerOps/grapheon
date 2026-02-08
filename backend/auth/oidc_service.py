"""
Multi-provider OIDC/OAuth2 service.

Handles provider discovery, authorization code exchange, userinfo fetching,
and role resolution from IdP claims.
Uses ``authlib`` for provider-agnostic OIDC and ``httpx`` for HTTP calls.
"""

import logging
from typing import Any, Dict, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import AuthProvider, RoleMapping

logger = logging.getLogger(__name__)


class OAuthTokenError(Exception):
    """Raised when an OAuth2 token exchange returns an error response."""


# Role priority: admin > editor > viewer
_ROLE_PRIORITY = {"viewer": 1, "editor": 2, "admin": 3}

# In-memory cache for OIDC discovery documents (issuer_url -> config)
_discovery_cache: Dict[str, Dict[str, str]] = {}


async def discover_endpoints(issuer_url: str) -> Dict[str, str]:
    """
    Perform OIDC discovery via ``.well-known/openid-configuration``.

    Results are cached in memory for the process lifetime.

    Args:
        issuer_url: Base issuer URL (e.g. ``https://auth.example.com``).

    Returns:
        Dict with ``authorization_endpoint``, ``token_endpoint``,
        ``userinfo_endpoint``, and ``jwks_uri``.
    """
    if issuer_url in _discovery_cache:
        return _discovery_cache[issuer_url]

    discovery_url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"

    async with httpx.AsyncClient() as client:
        resp = await client.get(discovery_url, timeout=10.0)
        resp.raise_for_status()
        config = resp.json()

    result = {
        "authorization_endpoint": config.get("authorization_endpoint", ""),
        "token_endpoint": config.get("token_endpoint", ""),
        "userinfo_endpoint": config.get("userinfo_endpoint", ""),
        "jwks_uri": config.get("jwks_uri", ""),
    }
    _discovery_cache[issuer_url] = result
    return result


async def exchange_code(
    provider: AuthProvider,
    code: str,
    redirect_uri: str,
    code_verifier: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Exchange an authorization code for tokens at the provider's token endpoint.

    Args:
        provider: AuthProvider model instance.
        code: Authorization code from IdP callback.
        redirect_uri: The redirect URI used in the original authorize request.
        code_verifier: PKCE code verifier (optional).

    Returns:
        Token response dict (``access_token``, ``id_token``, etc.).
    """
    token_endpoint = provider.token_endpoint
    if not token_endpoint:
        endpoints = await discover_endpoints(provider.issuer_url)
        token_endpoint = endpoints["token_endpoint"]

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier

    # Request JSON response — GitHub returns form-encoded by default
    headers = {"Accept": "application/json"}

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_endpoint, data=data, headers=headers, timeout=10.0,
        )
        resp.raise_for_status()

        # Some OAuth2 providers may still return form-encoded despite Accept header
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            result = resp.json()
        else:
            # Parse form-encoded: "access_token=xxx&token_type=bearer&scope=..."
            from urllib.parse import parse_qs

            parsed = parse_qs(resp.text)
            result = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    # GitHub (and some other OAuth2 providers) return errors as HTTP 200
    # with an "error" field instead of a proper HTTP error status.
    if "error" in result:
        error = result["error"]
        desc = result.get("error_description", "")
        raise OAuthTokenError(
            f"Token endpoint returned error: {error}"
            + (f" — {desc}" if desc else "")
        )

    if "access_token" not in result:
        raise OAuthTokenError(
            "Token endpoint response missing access_token"
        )

    return result


async def fetch_userinfo(
    provider: AuthProvider,
    access_token: str,
) -> Dict[str, Any]:
    """
    Fetch user information from the provider's userinfo endpoint.

    For OAuth2 providers that don't return standard OIDC claims (e.g. GitHub),
    the response is normalised so that downstream code can always rely on
    ``sub``, ``email``, ``name``, and ``preferred_username``.

    Args:
        provider: AuthProvider model instance.
        access_token: Bearer access token from token exchange.

    Returns:
        User info claims dict with at least ``sub``, ``email``,
        ``name``, and ``preferred_username`` keys.
    """
    userinfo_endpoint = provider.userinfo_endpoint
    if not userinfo_endpoint:
        endpoints = await discover_endpoints(provider.issuer_url)
        userinfo_endpoint = endpoints["userinfo_endpoint"]

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        claims = resp.json()

    # Normalise non-OIDC responses into standard claim names.
    # GitHub returns "id" (int), "login", "name", "email" (may be null).
    if "sub" not in claims and "id" in claims:
        claims["sub"] = str(claims["id"])
    if "preferred_username" not in claims and "login" in claims:
        claims["preferred_username"] = claims["login"]

    # GitHub may return email=null if the user's email is private.
    # In that case, fall back to fetching from /user/emails.
    if not claims.get("email") and provider.provider_type == "oauth2":
        claims["email"] = await _fetch_github_primary_email(
            userinfo_endpoint, access_token,
        )

    return claims


async def _fetch_github_primary_email(
    userinfo_endpoint: str,
    access_token: str,
) -> Optional[str]:
    """
    Try to fetch the user's primary verified email from the GitHub
    ``/user/emails`` endpoint. Returns ``None`` on failure.
    """
    # Only attempt if userinfo looks like the GitHub API
    if "api.github.com" not in userinfo_endpoint:
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            emails = resp.json()
            # Prefer primary+verified, fall back to first verified, then first
            for entry in emails:
                if entry.get("primary") and entry.get("verified"):
                    return entry["email"]
            for entry in emails:
                if entry.get("verified"):
                    return entry["email"]
            if emails:
                return emails[0].get("email")
    except Exception as exc:
        logger.warning(f"Failed to fetch GitHub user emails: {exc}")

    return None


async def resolve_role(
    db: AsyncSession,
    provider: AuthProvider,
    claims: Dict[str, Any],
) -> str:
    """
    Determine the application role from IdP claims using RoleMapping rules.

    All enabled mappings for this provider are evaluated against the claims.
    The highest-privilege matching role wins. If nothing matches, defaults
    to ``"viewer"``.

    Args:
        db: Database session.
        provider: AuthProvider model instance.
        claims: Decoded JWT claims or userinfo response.

    Returns:
        Role string: ``"admin"``, ``"editor"``, or ``"viewer"``.
    """
    result = await db.execute(
        select(RoleMapping).where(
            RoleMapping.provider_id == provider.id,
            RoleMapping.is_enabled.is_(True),
        )
    )
    mappings = result.scalars().all()

    best_role = "viewer"
    best_priority = _ROLE_PRIORITY[best_role]

    for mapping in mappings:
        # Navigate the claim path (supports dotted paths like "resource_access.app.roles")
        claim_value = _get_nested_claim(claims, mapping.idp_claim_path)

        if claim_value is None:
            continue

        # Check if the claim value matches (supports list membership or exact match)
        matched = False
        if isinstance(claim_value, list):
            matched = mapping.idp_claim_value in claim_value
        elif isinstance(claim_value, str):
            matched = claim_value == mapping.idp_claim_value

        if matched:
            priority = _ROLE_PRIORITY.get(mapping.app_role, 0)
            if priority > best_priority:
                best_role = mapping.app_role
                best_priority = priority

    return best_role


def _get_nested_claim(claims: Dict[str, Any], path: str) -> Any:
    """
    Navigate a dotted claim path to extract a value.

    Example: ``_get_nested_claim({"a": {"b": ["c"]}}, "a.b")`` returns ``["c"]``.
    """
    parts = path.split(".")
    current = claims
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current
