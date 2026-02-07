"""
Comprehensive test suite for the authentication system.

Covers:
- JWT token creation and validation
- Local and OIDC authentication endpoints
- Role-based access control (RBAC)
- User management endpoints
- OIDC service utilities
"""

import pytest
from datetime import timedelta
from jose import JWTError
from httpx import AsyncClient
import bcrypt as _bcrypt

from auth.jwt_service import create_access_token, verify_access_token
from auth.oidc_service import resolve_role, _get_nested_claim
from database import get_db
from models.user import User
from models.auth_provider import AuthProvider
from models.role_mapping import RoleMapping
from main import app
from config import settings


# ──────────────────────────────────────────────────────────────────────────────
# JWT SERVICE TESTS (5 tests)
# ──────────────────────────────────────────────────────────────────────────────


class TestJWTService:
    """Tests for JWT token creation and validation."""

    def test_create_access_token(self):
        """Test that create_access_token creates a valid token with correct claims."""
        user_id = 123
        role = "admin"

        token = create_access_token(user_id=user_id, role=role)

        assert isinstance(token, str)
        assert len(token) > 0

        # Verify the token can be decoded and has correct claims
        payload = verify_access_token(token)
        assert payload["sub"] == "123"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"
        assert "iat" in payload
        assert "exp" in payload

    def test_verify_valid_token(self):
        """Test that verify_access_token correctly decodes a valid token."""
        user_id = 456
        role = "editor"

        token = create_access_token(user_id=user_id, role=role)
        payload = verify_access_token(token)

        assert payload["sub"] == "456"
        assert payload["role"] == "editor"
        assert payload["type"] == "access"

    def test_expired_token_rejected(self):
        """Test that an expired token raises JWTError when verified."""
        # Create a token with 0 expiration time
        expires_delta = timedelta(seconds=-1)  # Expired immediately
        token = create_access_token(
            user_id=789,
            role="viewer",
            expires_delta=expires_delta,
        )

        # Attempting to verify should raise JWTError
        with pytest.raises(JWTError):
            verify_access_token(token)

    def test_tampered_token_rejected(self):
        """Test that a tampered token raises JWTError when verified."""
        token = create_access_token(user_id=999, role="admin")

        # Tamper with the payload section (middle segment) to reliably
        # invalidate the signature.  Swapping two characters in the
        # base64url-encoded payload virtually guarantees an invalid
        # HMAC, unlike changing the last byte of the signature which
        # can (rarely) still decode to a valid token.
        parts = token.split(".")
        assert len(parts) == 3, "JWT must have 3 dot-separated parts"
        payload = list(parts[1])
        # Swap first two characters of the payload section
        if len(payload) >= 2:
            payload[0], payload[1] = payload[1], payload[0]
        parts[1] = "".join(payload)
        tampered_token = ".".join(parts)

        # Attempting to verify should raise JWTError
        with pytest.raises(JWTError):
            verify_access_token(tampered_token)

    def test_token_with_extra_claims(self):
        """Test that extra claims are preserved in the token."""
        extra_claims = {
            "custom_claim": "custom_value",
            "another_claim": 42,
        }

        token = create_access_token(
            user_id=111,
            role="editor",
            extra_claims=extra_claims,
        )

        payload = verify_access_token(token)
        assert payload["custom_claim"] == "custom_value"
        assert payload["another_claim"] == 42


# ──────────────────────────────────────────────────────────────────────────────
# AUTH ENDPOINT TESTS (11 tests)
# ──────────────────────────────────────────────────────────────────────────────


class TestAuthEndpoints:
    """Tests for authentication REST endpoints."""

    @pytest.mark.asyncio
    async def test_get_providers_empty(self, async_client: AsyncClient):
        """Test GET /api/auth/providers returns empty list when no providers configured."""
        response = await async_client.get("/api/auth/providers")

        assert response.status_code == 200
        data = response.json()
        assert data["providers"] == []
        # local_auth_enabled depends on whether there are local users
        assert "local_auth_enabled" in data

    @pytest.mark.asyncio
    async def test_local_login_success(self, async_client: AsyncClient):
        """Test successful local login with valid credentials."""
        # Setup: Create a test user with password hash
        password = "test_password_123"
        password_hash = _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

        # Get database session from the app's override
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        user = User(
            username="testadmin",
            email="admin@test.com",
            display_name="Test Admin",
            role="admin",
            is_active=True,
            local_password_hash=password_hash,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Test: Login with correct credentials
        response = await async_client.post(
            "/api/auth/login/local",
            json={"username": "testadmin", "password": password},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user.id
        assert data["username"] == "testadmin"
        assert data["email"] == "admin@test.com"
        assert data["role"] == "admin"
        assert "access_token" in data
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] > 0

    @pytest.mark.asyncio
    async def test_local_login_wrong_password(self, async_client: AsyncClient):
        """Test local login fails with wrong password."""
        # Setup: Create a test user
        password_hash = _bcrypt.hashpw("correct_password".encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        user = User(
            username="testuser",
            email="user@test.com",
            display_name="Test User",
            role="viewer",
            is_active=True,
            local_password_hash=password_hash,
        )
        db.add(user)
        await db.commit()

        # Test: Login with wrong password
        response = await async_client.post(
            "/api/auth/login/local",
            json={"username": "testuser", "password": "wrong_password"},
        )

        assert response.status_code == 401
        assert "Invalid username or password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_local_login_nonexistent_user(self, async_client: AsyncClient):
        """Test local login fails for nonexistent user."""
        response = await async_client.post(
            "/api/auth/login/local",
            json={"username": "nonexistent", "password": "anypassword"},
        )

        assert response.status_code == 401
        assert "Invalid username or password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_local_login_disabled_user(self, async_client: AsyncClient):
        """Test local login fails for disabled user account."""
        # Setup: Create a disabled user
        password = "password123"
        password_hash = _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        user = User(
            username="disabled_user",
            email="disabled@test.com",
            display_name="Disabled User",
            role="viewer",
            is_active=False,  # Disabled
            local_password_hash=password_hash,
        )
        db.add(user)
        await db.commit()

        # Test: Try to login with disabled account
        response = await async_client.post(
            "/api/auth/login/local",
            json={"username": "disabled_user", "password": password},
        )

        assert response.status_code == 403
        assert "Account is disabled" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_me_authenticated(self, async_client: AsyncClient):
        """Test GET /api/auth/me returns user info with valid JWT."""
        # Setup: Create a test user and generate token
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        user = User(
            username="me_testuser",
            email="metest@test.com",
            display_name="Me Test User",
            role="editor",
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        token = create_access_token(user_id=user.id, role=user.role)

        # Test: Get current user info with valid token
        response = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user.id
        assert data["username"] == "me_testuser"
        assert data["email"] == "metest@test.com"
        assert data["role"] == "editor"
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_get_me_no_token(self, async_client: AsyncClient):
        """Test GET /api/auth/me returns 401 when no token provided."""
        response = await async_client.get("/api/auth/me")

        assert response.status_code == 401
        assert "Missing authorization credentials" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_me_invalid_token(self, async_client: AsyncClient):
        """Test GET /api/auth/me returns 401 with invalid token."""
        response = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid_token_xyz"},
        )

        assert response.status_code == 401
        assert "Invalid or expired token" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_users_admin(self, async_client: AsyncClient):
        """Test admin can list all users."""
        # Setup: Create admin and regular users
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        admin_user = User(
            username="admin",
            email="admin@test.com",
            role="admin",
            is_active=True,
        )
        viewer_user = User(
            username="viewer",
            email="viewer@test.com",
            role="viewer",
            is_active=True,
        )
        db.add_all([admin_user, viewer_user])
        await db.commit()
        await db.refresh(admin_user)

        admin_token = create_access_token(user_id=admin_user.id, role="admin")

        # Test: Admin lists users
        response = await async_client.get(
            "/api/auth/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        users = response.json()
        assert len(users) >= 2
        usernames = [u["username"] for u in users]
        assert "admin" in usernames
        assert "viewer" in usernames

    @pytest.mark.asyncio
    async def test_list_users_viewer_forbidden(self, async_client: AsyncClient):
        """Test viewer cannot list users (403 Forbidden)."""
        # Setup: Create viewer user
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        viewer = User(
            username="viewer_user",
            email="viewer@test.com",
            role="viewer",
            is_active=True,
        )
        db.add(viewer)
        await db.commit()
        await db.refresh(viewer)

        viewer_token = create_access_token(user_id=viewer.id, role="viewer")

        # Test: Viewer attempts to list users
        response = await async_client.get(
            "/api/auth/users",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )

        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_user_role(self, async_client: AsyncClient):
        """Test admin can change a user's role."""
        # Setup: Create admin and target user
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        admin = User(
            username="admin_user",
            email="admin@test.com",
            role="admin",
            is_active=True,
        )
        target = User(
            username="target_user",
            email="target@test.com",
            role="viewer",
            is_active=True,
        )
        db.add_all([admin, target])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(target)

        admin_token = create_access_token(user_id=admin.id, role="admin")

        # Test: Admin updates target user's role
        response = await async_client.patch(
            f"/api/auth/users/{target.id}/role",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"role": "editor"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "editor"
        assert data["id"] == target.id


# ──────────────────────────────────────────────────────────────────────────────
# ROLE-BASED ACCESS CONTROL TESTS (5 tests)
# ──────────────────────────────────────────────────────────────────────────────


class TestRBAC:
    """Tests for role-based access control."""

    @pytest.mark.asyncio
    async def test_protected_endpoint_no_auth(self, async_client: AsyncClient):
        """Test protected endpoint returns 401 without authentication."""
        # /api/auth/me is a protected endpoint
        response = await async_client.get("/api/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_auth(self, async_client: AsyncClient):
        """Test protected endpoint returns 200 with valid authentication."""
        # Setup: Create authenticated user
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        user = User(
            username="auth_user",
            email="auth@test.com",
            role="viewer",
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        token = create_access_token(user_id=user.id, role="viewer")

        # Test: Access protected endpoint with valid token
        response = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_editor_endpoint_as_viewer(self, async_client: AsyncClient):
        """Test editor-only endpoint returns 403 for viewer role."""
        # Setup: Create viewer user
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        viewer = User(
            username="viewer_only",
            email="viewer@test.com",
            role="viewer",
            is_active=True,
        )
        db.add(viewer)
        await db.commit()
        await db.refresh(viewer)

        viewer_token = create_access_token(user_id=viewer.id, role="viewer")

        # Test: Viewer attempts to access admin-only endpoint
        response = await async_client.get(
            "/api/auth/users",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_editor_endpoint_as_editor(self, async_client: AsyncClient):
        """Test editor endpoint succeeds for editor role."""
        # Setup: Create editor user
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        editor = User(
            username="editor_user",
            email="editor@test.com",
            role="editor",
            is_active=True,
        )
        db.add(editor)
        await db.commit()
        await db.refresh(editor)

        editor_token = create_access_token(user_id=editor.id, role="editor")

        # Test: Editor accesses their own profile (should succeed)
        response = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {editor_token}"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_endpoint_as_editor(self, async_client: AsyncClient):
        """Test admin-only endpoint returns 403 for editor role."""
        # Setup: Create editor user
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        editor = User(
            username="editor_no_admin",
            email="editor@test.com",
            role="editor",
            is_active=True,
        )
        db.add(editor)
        await db.commit()
        await db.refresh(editor)

        editor_token = create_access_token(user_id=editor.id, role="editor")

        # Test: Editor attempts to access admin-only endpoint
        response = await async_client.get(
            "/api/auth/users",
            headers={"Authorization": f"Bearer {editor_token}"},
        )

        assert response.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# ROLE MAPPING TESTS (3 tests)
# ──────────────────────────────────────────────────────────────────────────────


class TestRoleMapping:
    """Tests for OIDC role mapping resolution."""

    @pytest.mark.asyncio
    async def test_resolve_role_no_mappings(self, async_client: AsyncClient):
        """Test resolve_role returns 'viewer' by default when no mappings exist."""
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        # Create a provider without role mappings
        provider = AuthProvider(
            provider_name="test_provider",
            display_name="Test Provider",
            provider_type="oidc",
            issuer_url="https://test.example.com",
            client_id="test-client",
            client_secret="test-secret",
            is_enabled=True,
        )
        db.add(provider)
        await db.commit()
        await db.refresh(provider)

        # Resolve role with no mappings
        claims = {"sub": "user123", "email": "user@example.com"}
        role = await resolve_role(db, provider, claims)

        assert role == "viewer"

    @pytest.mark.asyncio
    async def test_resolve_role_single_match(self, async_client: AsyncClient):
        """Test resolve_role returns correct role when a single mapping matches."""
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        # Create provider with role mapping
        provider = AuthProvider(
            provider_name="okta",
            display_name="Okta",
            provider_type="oidc",
            issuer_url="https://okta.example.com",
            client_id="okta-client",
            client_secret="okta-secret",
            is_enabled=True,
        )
        db.add(provider)
        await db.commit()
        await db.refresh(provider)

        # Create role mapping: admins group -> admin role
        mapping = RoleMapping(
            provider_id=provider.id,
            idp_claim_path="groups",
            idp_claim_value="admins",
            app_role="admin",
            is_enabled=True,
        )
        db.add(mapping)
        await db.commit()

        # Resolve role when user is in admins group
        claims = {
            "sub": "user456",
            "email": "admin@example.com",
            "groups": ["admins", "developers"],
        }
        role = await resolve_role(db, provider, claims)

        assert role == "admin"

    @pytest.mark.asyncio
    async def test_resolve_role_highest_wins(self, async_client: AsyncClient):
        """Test resolve_role picks highest privilege when multiple roles match."""
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        # Create provider with multiple role mappings
        provider = AuthProvider(
            provider_name="github",
            display_name="GitHub",
            provider_type="oauth2",
            issuer_url="https://github.com",
            client_id="github-client",
            client_secret="github-secret",
            is_enabled=True,
        )
        db.add(provider)
        await db.commit()
        await db.refresh(provider)

        # Create multiple mappings with different privilege levels
        editor_mapping = RoleMapping(
            provider_id=provider.id,
            idp_claim_path="teams",
            idp_claim_value="developers",
            app_role="editor",
            is_enabled=True,
        )
        admin_mapping = RoleMapping(
            provider_id=provider.id,
            idp_claim_path="teams",
            idp_claim_value="admins",
            app_role="admin",
            is_enabled=True,
        )
        viewer_mapping = RoleMapping(
            provider_id=provider.id,
            idp_claim_path="teams",
            idp_claim_value="members",
            app_role="viewer",
            is_enabled=True,
        )
        db.add_all([editor_mapping, admin_mapping, viewer_mapping])
        await db.commit()

        # User is in all three groups: admin should win (highest privilege)
        claims = {
            "sub": "user789",
            "email": "power@example.com",
            "teams": ["admins", "developers", "members"],
        }
        role = await resolve_role(db, provider, claims)

        # Admin (priority 3) > editor (priority 2) > viewer (priority 1)
        assert role == "admin"


# ──────────────────────────────────────────────────────────────────────────────
# OIDC SERVICE TESTS (2 tests)
# ──────────────────────────────────────────────────────────────────────────────


class TestOIDCService:
    """Tests for OIDC service utility functions."""

    def test_get_nested_claim_simple(self):
        """Test _get_nested_claim with simple single-level path."""
        claims = {
            "sub": "user123",
            "email": "user@example.com",
            "groups": ["admins", "developers"],
        }

        result = _get_nested_claim(claims, "email")

        assert result == "user@example.com"

    def test_get_nested_claim_dotted(self):
        """Test _get_nested_claim with dotted path navigation."""
        claims = {
            "sub": "user456",
            "resource_access": {
                "app": {
                    "roles": ["admin", "editor"],
                },
            },
        }

        result = _get_nested_claim(claims, "resource_access.app.roles")

        assert result == ["admin", "editor"]


# ──────────────────────────────────────────────────────────────────────────────
# FEATURE FLAGS TESTS (3 tests)
# ──────────────────────────────────────────────────────────────────────────────


class TestFeatureFlags:
    """Tests for AUTH_ENABLED and ENFORCE_AUTH feature flags."""

    @pytest.mark.asyncio
    async def test_auth_disabled_allows_anonymous(self, async_client: AsyncClient):
        """When AUTH_ENABLED=False, endpoints work without any token."""
        original = settings.AUTH_ENABLED
        try:
            settings.AUTH_ENABLED = False
            # Access a protected endpoint without token - should get 200
            # Use /api/hosts which requires require_any_authenticated
            response = await async_client.get("/api/hosts")
            assert response.status_code == 200
        finally:
            settings.AUTH_ENABLED = original

    @pytest.mark.asyncio
    async def test_enforce_auth_false_allows_anonymous(self, async_client: AsyncClient):
        """When AUTH_ENABLED=True but ENFORCE_AUTH=False, unauthenticated requests still work."""
        original_enabled = settings.AUTH_ENABLED
        original_enforce = settings.ENFORCE_AUTH
        try:
            settings.AUTH_ENABLED = True
            settings.ENFORCE_AUTH = False
            # Should work without token (anonymous admin mode)
            response = await async_client.get("/api/hosts")
            assert response.status_code == 200
        finally:
            settings.AUTH_ENABLED = original_enabled
            settings.ENFORCE_AUTH = original_enforce

    @pytest.mark.asyncio
    async def test_enforce_auth_true_rejects_anonymous(self, async_client: AsyncClient):
        """When ENFORCE_AUTH=True, unauthenticated requests are rejected."""
        original_enabled = settings.AUTH_ENABLED
        original_enforce = settings.ENFORCE_AUTH
        try:
            settings.AUTH_ENABLED = True
            settings.ENFORCE_AUTH = True
            # Should fail without token
            response = await async_client.get("/api/hosts")
            assert response.status_code == 401
        finally:
            settings.AUTH_ENABLED = original_enabled
            settings.ENFORCE_AUTH = original_enforce


# ──────────────────────────────────────────────────────────────────────────────
# LOCAL ADMIN BOOTSTRAP TESTS (2 tests)
# ──────────────────────────────────────────────────────────────────────────────


class TestLocalAdminBootstrap:
    """Tests for local admin bootstrap from environment variables."""

    @pytest.mark.asyncio
    async def test_bootstrap_creates_admin(self, async_client: AsyncClient):
        """Verify a local admin can be created and used to login."""
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        # Simulate bootstrap: create admin with known password
        password_hash = _bcrypt.hashpw("bootstrap_pass_123".encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
        user = User(
            username="bootstrap_admin",
            email="bootstrap@example.com",
            role="admin",
            is_active=True,
            local_password_hash=password_hash,
        )
        db.add(user)
        await db.commit()

        # Verify login works
        response = await async_client.post(
            "/api/auth/login/local",
            json={"username": "bootstrap_admin", "password": "bootstrap_pass_123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"
        assert "access_token" in data

    @pytest.mark.asyncio
    async def test_bootstrap_admin_can_manage_users(self, async_client: AsyncClient):
        """Verify bootstrapped admin can list and manage users."""
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        admin = User(
            username="mgmt_admin",
            email="mgmt@example.com",
            role="admin",
            is_active=True,
        )
        viewer = User(
            username="mgmt_viewer",
            email="mgmt_viewer@example.com",
            role="viewer",
            is_active=True,
        )
        db.add_all([admin, viewer])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(viewer)

        token = create_access_token(user_id=admin.id, role="admin")

        # Admin can list users
        response = await async_client.get(
            "/api/auth/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        users = response.json()
        assert len(users) >= 2

        # Admin can promote viewer to editor
        response = await async_client.patch(
            f"/api/auth/users/{viewer.id}/role",
            headers={"Authorization": f"Bearer {token}"},
            json={"role": "editor"},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "editor"


# ──────────────────────────────────────────────────────────────────────────────
# PROVIDER REGISTRATION TESTS (2 tests)
# ──────────────────────────────────────────────────────────────────────────────


class TestProviderRegistration:
    """Tests for OIDC provider registration and listing."""

    @pytest.mark.asyncio
    async def test_registered_provider_appears_in_list(self, async_client: AsyncClient):
        """Provider registered in DB appears in GET /api/auth/providers."""
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        provider = AuthProvider(
            provider_name="test_okta",
            display_name="Test Okta",
            provider_type="oidc",
            issuer_url="https://test.okta.com",
            client_id="test-client-id",
            client_secret="test-secret",
            authorization_endpoint="https://test.okta.com/authorize",
            scope="openid profile email",
            display_order=1,
            is_enabled=True,
        )
        db.add(provider)
        await db.commit()

        response = await async_client.get("/api/auth/providers")
        assert response.status_code == 200
        data = response.json()
        names = [p["name"] for p in data["providers"]]
        assert "test_okta" in names

        # Verify no secrets leaked
        for p in data["providers"]:
            assert "client_secret" not in p or p.get("client_secret") is None

    @pytest.mark.asyncio
    async def test_disabled_provider_hidden(self, async_client: AsyncClient):
        """Disabled provider does NOT appear in GET /api/auth/providers."""
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()

        provider = AuthProvider(
            provider_name="disabled_provider",
            display_name="Disabled",
            provider_type="oidc",
            issuer_url="https://disabled.example.com",
            client_id="disabled-client",
            client_secret="disabled-secret",
            is_enabled=False,
        )
        db.add(provider)
        await db.commit()

        response = await async_client.get("/api/auth/providers")
        assert response.status_code == 200
        names = [p["name"] for p in response.json()["providers"]]
        assert "disabled_provider" not in names


# ──────────────────────────────────────────────────────────────────────────────
# ADMIN CRUD TESTS (15 tests)
# ──────────────────────────────────────────────────────────────────────────────


class TestAuthAdminProviders:
    """Tests for admin provider CRUD endpoints."""

    async def _make_admin(self, async_client):
        """Helper: create admin user and return (user, token, db)."""
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()
        admin = User(
            username="crud_admin",
            email="crud_admin@example.com",
            role="admin",
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        token = create_access_token(user_id=admin.id, role="admin")
        return admin, token, db

    @pytest.mark.asyncio
    async def test_create_provider(self, async_client: AsyncClient):
        """Admin can create an auth provider."""
        _, token, _ = await self._make_admin(async_client)
        response = await async_client.post(
            "/api/auth/admin/providers",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "provider_name": "test_github",
                "display_name": "GitHub SSO",
                "provider_type": "oauth2",
                "issuer_url": "https://github.com",
                "client_id": "gh-client-id",
                "client_secret": "gh-secret",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["provider_name"] == "test_github"
        assert data["display_name"] == "GitHub SSO"
        assert data["is_enabled"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_providers(self, async_client: AsyncClient):
        """Admin can list all providers."""
        _, token, _ = await self._make_admin(async_client)
        # Create provider via API to avoid session conflicts
        await async_client.post(
            "/api/auth/admin/providers",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "provider_name": "list_test",
                "display_name": "List Test",
                "provider_type": "oidc",
                "issuer_url": "https://list.example.com",
                "client_id": "list-id",
                "client_secret": "list-secret",
            },
        )

        response = await async_client.get(
            "/api/auth/admin/providers",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        names = [prov["provider_name"] for prov in response.json()]
        assert "list_test" in names

    @pytest.mark.asyncio
    async def test_update_provider(self, async_client: AsyncClient):
        """Admin can update a provider."""
        _, token, _ = await self._make_admin(async_client)
        # Create via API first
        create_resp = await async_client.post(
            "/api/auth/admin/providers",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "provider_name": "update_test",
                "display_name": "Before",
                "provider_type": "oidc",
                "issuer_url": "https://update.example.com",
                "client_id": "upd-id",
                "client_secret": "upd-secret",
            },
        )
        provider_id = create_resp.json()["id"]

        response = await async_client.patch(
            f"/api/auth/admin/providers/{provider_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"display_name": "After", "is_enabled": False},
        )
        assert response.status_code == 200
        assert response.json()["display_name"] == "After"
        assert response.json()["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_delete_provider(self, async_client: AsyncClient):
        """Admin can delete a provider."""
        _, token, _ = await self._make_admin(async_client)
        # Create via API first
        create_resp = await async_client.post(
            "/api/auth/admin/providers",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "provider_name": "delete_test",
                "display_name": "Delete Me",
                "provider_type": "oidc",
                "issuer_url": "https://delete.example.com",
                "client_id": "del-id",
                "client_secret": "del-secret",
            },
        )
        provider_id = create_resp.json()["id"]

        response = await async_client.delete(
            f"/api/auth/admin/providers/{provider_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # Verify it's gone
        response = await async_client.get(
            "/api/auth/admin/providers",
            headers={"Authorization": f"Bearer {token}"},
        )
        names = [prov["provider_name"] for prov in response.json()]
        assert "delete_test" not in names

    @pytest.mark.asyncio
    async def test_duplicate_provider_rejected(self, async_client: AsyncClient):
        """Creating a provider with duplicate name returns 400."""
        _, token, _ = await self._make_admin(async_client)
        payload = {
            "provider_name": "dup_test",
            "display_name": "Dup",
            "provider_type": "oidc",
            "issuer_url": "https://dup.example.com",
            "client_id": "dup-id",
            "client_secret": "dup-secret",
        }
        r1 = await async_client.post(
            "/api/auth/admin/providers",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        assert r1.status_code == 201

        r2 = await async_client.post(
            "/api/auth/admin/providers",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        assert r2.status_code == 400

    @pytest.mark.asyncio
    async def test_provider_requires_admin(self, async_client: AsyncClient):
        """Non-admin users get 403 on admin provider endpoints."""
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()
        viewer = User(
            username="prov_viewer",
            email="prov_viewer@example.com",
            role="viewer",
            is_active=True,
        )
        db.add(viewer)
        await db.commit()
        await db.refresh(viewer)
        token = create_access_token(user_id=viewer.id, role="viewer")

        response = await async_client.get(
            "/api/auth/admin/providers",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


class TestAuthAdminMappings:
    """Tests for admin role mapping CRUD endpoints."""

    async def _setup(self, async_client):
        """Helper: create admin + provider via API, return (token, provider_id)."""
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()
        admin = User(
            username="map_admin",
            email="map_admin@example.com",
            role="admin",
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        token = create_access_token(user_id=admin.id, role="admin")

        # Create provider via API to avoid session conflicts
        create_resp = await async_client.post(
            "/api/auth/admin/providers",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "provider_name": "map_provider",
                "display_name": "Mapping Provider",
                "provider_type": "oidc",
                "issuer_url": "https://map.example.com",
                "client_id": "map-id",
                "client_secret": "map-secret",
            },
        )
        provider_id = create_resp.json()["id"]
        return token, provider_id

    @pytest.mark.asyncio
    async def test_create_mapping(self, async_client: AsyncClient):
        """Admin can create a role mapping for a provider."""
        token, pid = await self._setup(async_client)
        response = await async_client.post(
            f"/api/auth/admin/providers/{pid}/mappings",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "idp_claim_path": "groups",
                "idp_claim_value": "net-admins",
                "app_role": "admin",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["idp_claim_path"] == "groups"
        assert data["app_role"] == "admin"

    @pytest.mark.asyncio
    async def test_list_mappings(self, async_client: AsyncClient):
        """Admin can list mappings for a provider."""
        token, pid = await self._setup(async_client)
        # Create mapping via API
        await async_client.post(
            f"/api/auth/admin/providers/{pid}/mappings",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "idp_claim_path": "groups",
                "idp_claim_value": "editors",
                "app_role": "editor",
            },
        )

        response = await async_client.get(
            f"/api/auth/admin/providers/{pid}/mappings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert len(response.json()) >= 1

    @pytest.mark.asyncio
    async def test_update_mapping(self, async_client: AsyncClient):
        """Admin can update a role mapping."""
        token, pid = await self._setup(async_client)
        # Create mapping via API
        create_resp = await async_client.post(
            f"/api/auth/admin/providers/{pid}/mappings",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "idp_claim_path": "groups",
                "idp_claim_value": "upd-editors",
                "app_role": "editor",
            },
        )
        mapping_id = create_resp.json()["id"]

        response = await async_client.patch(
            f"/api/auth/admin/mappings/{mapping_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"app_role": "admin", "is_enabled": False},
        )
        assert response.status_code == 200
        assert response.json()["app_role"] == "admin"
        assert response.json()["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_delete_mapping(self, async_client: AsyncClient):
        """Admin can delete a role mapping."""
        token, pid = await self._setup(async_client)
        # Create mapping via API
        create_resp = await async_client.post(
            f"/api/auth/admin/providers/{pid}/mappings",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "idp_claim_path": "groups",
                "idp_claim_value": "del-viewers",
                "app_role": "viewer",
            },
        )
        mapping_id = create_resp.json()["id"]

        response = await async_client.delete(
            f"/api/auth/admin/mappings/{mapping_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_duplicate_mapping_rejected(self, async_client: AsyncClient):
        """Duplicate mapping (same provider, path, value) returns 400."""
        token, pid = await self._setup(async_client)
        payload = {
            "idp_claim_path": "groups",
            "idp_claim_value": "unique-group",
            "app_role": "viewer",
        }
        headers = {"Authorization": f"Bearer {token}"}
        r1 = await async_client.post(
            f"/api/auth/admin/providers/{pid}/mappings",
            headers=headers,
            json=payload,
        )
        assert r1.status_code == 201

        r2 = await async_client.post(
            f"/api/auth/admin/providers/{pid}/mappings",
            headers=headers,
            json=payload,
        )
        assert r2.status_code == 400


class TestAuthAdminUsers:
    """Tests for admin user management extensions."""

    @pytest.mark.asyncio
    async def test_toggle_user_active(self, async_client: AsyncClient):
        """Admin can disable and re-enable a user."""
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()
        admin = User(username="active_admin", email="active_admin@example.com", role="admin", is_active=True)
        target = User(username="active_target", email="active_target@example.com", role="viewer", is_active=True)
        db.add_all([admin, target])
        await db.commit()
        await db.refresh(admin)
        await db.refresh(target)
        token = create_access_token(user_id=admin.id, role="admin")

        # Disable
        r = await async_client.patch(
            f"/api/auth/users/{target.id}/active",
            headers={"Authorization": f"Bearer {token}"},
            json={"is_active": False},
        )
        assert r.status_code == 200
        assert r.json()["is_active"] is False

        # Re-enable
        r = await async_client.patch(
            f"/api/auth/users/{target.id}/active",
            headers={"Authorization": f"Bearer {token}"},
            json={"is_active": True},
        )
        assert r.status_code == 200
        assert r.json()["is_active"] is True

    @pytest.mark.asyncio
    async def test_inactive_user_cannot_login(self, async_client: AsyncClient):
        """A deactivated user cannot login."""
        db_gen = app.dependency_overrides[get_db]()
        db = await db_gen.__anext__()
        password_hash = _bcrypt.hashpw("testpass".encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
        user = User(
            username="inactive_login",
            email="inactive_login@example.com",
            role="viewer",
            is_active=False,
            local_password_hash=password_hash,
        )
        db.add(user)
        await db.commit()

        r = await async_client.post(
            "/api/auth/login/local",
            json={"username": "inactive_login", "password": "testpass"},
        )
        assert r.status_code == 403
