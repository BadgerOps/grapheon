# Graphēon Authentication Provider Setup Guide

**Version:** 1.0
**For:** Graphēon v0.8.0+
**Last Updated:** February 2026

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start — Local Admin Only](#quick-start--local-admin-only)
3. [Gradual Rollout Strategy](#gradual-rollout-strategy)
4. [Configuring OIDC Providers](#configuring-oidc-providers)
5. [Role Mapping](#role-mapping)
6. [Docker / Container Setup](#docker--container-setup)
7. [Systemd / Podman Setup](#systemd--podman-setup)
8. [API Reference](#api-reference)
9. [Troubleshooting](#troubleshooting)
10. [Security Considerations](#security-considerations)

---

## Overview

Graphēon v0.8.0 introduces a complete authentication and authorization system designed for enterprise network topology management. The system provides:

- **Three-tier role-based access control (RBAC):**
  - **Admin:** Full access to all features, user management, maintenance, backups
  - **Editor:** Can import/export data, manage network topology (hosts, VLANs, devices, correlations), plus all viewer permissions
  - **Viewer:** Read-only access to hosts, connections, ARP tables, network map, search, and audit logs

- **Multiple authentication backends:**
  - Local username/password (with bcrypt hashing)
  - OpenID Connect (OIDC) providers (generic, Authentik, Keycloak, Okta, Google, GitHub, GitLab)
  - OAuth2 providers (for non-OIDC implementations)

- **Flexible deployment modes:**
  - **Public mode** (optional): All endpoints are public; one synthetic admin user
  - **Transition mode** (AUTH_ENABLED=true, ENFORCE_AUTH=false): Unauthenticated requests get anonymous admin access
  - **Production mode** (AUTH_ENABLED=true, ENFORCE_AUTH=true): All endpoints require valid JWT

- **JWT-based stateless authentication:**
  - HMAC HS256 signing
  - Configurable expiration (default: 60 minutes)
  - OIDC integration with PKCE support
  - Claims-based role mapping

---

## Quick Start — Local Admin Only

The simplest deployment: bootstrap a local admin account and use it exclusively.

### Setup

Set these three environment variables before starting Graphēon:

```bash
export LOCAL_ADMIN_USERNAME="admin"
export LOCAL_ADMIN_EMAIL="admin@example.com"
export LOCAL_ADMIN_PASSWORD="YourSecurePasswordHere"
```

Then start the application:

```bash
docker run -d \
  -p 8000:8000 \
  -v grapheon-db:/app/data \
  -e LOCAL_ADMIN_USERNAME="admin" \
  -e LOCAL_ADMIN_EMAIL="admin@example.com" \
  -e LOCAL_ADMIN_PASSWORD="YourSecurePasswordHere" \
  grapheon:latest
```

On first startup, Graphēon will:
1. Create the `admin` user with the password you provided (hashed with bcrypt)
2. Assign the admin role automatically
3. Return this account for all API authentication

### Accessing the Application

- **Frontend:** Navigate to `http://localhost:8000`
- **Login:** Use username `admin` with your password via the Local Login form
- **Token storage:** The JWT is stored in browser localStorage

If the `admin` user already exists (from a previous startup), the new credentials are ignored—only the first bootstrap succeeds.

### Notes

- No OIDC providers are configured
- Endpoints use role requirements, but full JWT enforcement requires `ENFORCE_AUTH=True`
- The admin user has full access
- Change `LOCAL_ADMIN_PASSWORD` on each startup if you want to rotate it, but only the initial value is used
- **Always set a strong password in production**

---

## Gradual Rollout Strategy

Most production deployments should roll out auth gradually using feature flags. This allows teams to test and migrate without disruption.

### Phase 1: Pilot Testing (Development)

Use explicit development settings if you want all endpoints public:

```bash
AUTH_ENABLED=False
ENFORCE_AUTH=False
```

Behavior:
- All endpoints are accessible without authentication
- A synthetic admin user is automatically created for API access
- Ideal for testing auth code paths without requiring external setup

### Phase 2: Auth Enabled, Unauthenticated = Anonymous Admin (Staging)

Enable auth but allow unauthenticated requests:

```bash
AUTH_ENABLED=True
ENFORCE_AUTH=False
LOCAL_ADMIN_USERNAME="admin"
LOCAL_ADMIN_EMAIL="admin@staging.local"
LOCAL_ADMIN_PASSWORD="StagingPassword123!"
```

Behavior:
- Auth system is active (JWT validation runs)
- Unauthenticated requests are given anonymous admin access (maximum permissiveness)
- Authenticated users use their real roles
- Allows users to log in at their own pace
- Gives teams time to configure OIDC providers

**Recommended duration:** 2–4 weeks

### Phase 3: Production (Enforce Auth)

Require authentication on all requests:

```bash
AUTH_ENABLED=True
ENFORCE_AUTH=True
JWT_SECRET="your-production-secret-key-min-32-chars"
LOCAL_ADMIN_USERNAME="admin"
LOCAL_ADMIN_EMAIL="admin@example.com"
LOCAL_ADMIN_PASSWORD="ProductionAdminPassword"
```

Behavior:
- All endpoints require a valid JWT or are rejected with 401 Unauthorized
- Unauthenticated requests cannot access the application
- OIDC providers and local login are the only entry points
- Role-based access control is strictly enforced

**Migration checklist:**
- [ ] Ensure all team members have accounts
- [ ] Test OIDC provider(s) with a sample of users
- [ ] Verify role mappings are correct
- [ ] Set up monitoring for 401 errors
- [ ] Plan a rollout window (minimize disruption)
- [ ] Communicate the change to users

---

## Configuring OIDC Providers

OIDC providers are registered by inserting rows into the `auth_providers` database table. Each provider can have multiple associated role mappings.

### Prerequisites

- Access to the SQLite database (typically at `/app/data/network.db` in containers)
- OIDC provider credentials (client_id, client_secret)
- Redirect URI: `https://your-domain.com/auth/callback` (or `http://localhost:8000/auth/callback` for development)

### General OIDC Configuration

All OIDC providers require:

| Field | Example |
|-------|---------|
| `provider_name` | `authentik_prod` (unique identifier) |
| `display_name` | `Authentik (Corporate)` (shown on login page) |
| `provider_type` | `oidc` |
| `issuer_url` | `https://auth.example.com` |
| `client_id` | `ABC123XYZ` |
| `client_secret` | `supersecret123` |
| `scope` | `openid profile email groups` |
| `display_order` | `1` (lower = earlier on login page) |
| `is_enabled` | `1` (1 = yes, 0 = no) |

The `authorization_endpoint`, `token_endpoint`, and `userinfo_endpoint` can be discovered automatically from the issuer's `.well-known/openid-configuration` endpoint, or specified manually.

### 1. Generic OIDC (Authentik, Keycloak, etc.)

#### Step 1: Create OAuth2 Application in Your OIDC Provider

**Authentik:**
1. Log in to Authentik admin panel
2. Navigate to **Applications** → **OAuth2/OpenID Provider** → **Create**
3. Set these fields:
   - **Name:** `Grapheon`
   - **Slug:** `grapheon`
   - **Redirect URIs:** `https://your-domain.com/auth/callback`
   - **Authorization flow:** Choose one with implicit approval or user consent
   - **Client type:** Confidential
4. Save. Note the **Client ID** and **Client Secret**.

**Keycloak:**
1. Log in to Keycloak admin console
2. Select your realm → **Clients** → **Create**
3. Set:
   - **Client ID:** `grapheon`
   - **Client Protocol:** `openid-connect`
4. On the Settings tab:
   - **Valid Redirect URIs:** `https://your-domain.com/auth/callback`
   - **Access Type:** Confidential
5. Go to the Credentials tab. Note the **Secret**.

#### Step 2: Register Provider in Graphēon

Use `sqlite3` to insert the provider record:

```bash
sqlite3 /app/data/network.db << 'EOF'
INSERT INTO auth_providers (
  provider_name,
  display_name,
  provider_type,
  issuer_url,
  client_id,
  client_secret,
  scope,
  display_order,
  is_enabled,
  created_at
) VALUES (
  'authentik_prod',
  'Authentik (Corporate)',
  'oidc',
  'https://auth.example.com',
  'ABC123XYZ',
  'supersecret123',
  'openid profile email groups',
  1,
  1,
  datetime('now')
);
EOF
```

The backend will automatically fetch discovery endpoints from `https://auth.example.com/.well-known/openid-configuration`.

#### Step 3: Verify

On the login page, you should see a button for "Authentik (Corporate)".

---

### 2. Okta

#### Step 1: Create OIDC Application in Okta

1. Log in to your Okta admin dashboard
2. **Applications** → **Applications** → **Create App Integration**
3. Choose **OIDC - OpenID Connect** → **Web Application**
4. Fill in:
   - **App name:** `Grapheon`
   - **Sign-in redirect URIs:** `https://your-domain.com/auth/callback`
   - **Sign-out redirect URIs:** (optional)
   - **Allowed grant types:** Authorization Code, Refresh Token
5. Save the app. Note:
   - **Client ID** (from the app details)
   - **Client Secret** (from the app details)
   - **Okta domain:** e.g., `https://dev-12345678.okta.com`

#### Step 2: Register Provider in Graphēon

```bash
sqlite3 /app/data/network.db << 'EOF'
INSERT INTO auth_providers (
  provider_name,
  display_name,
  provider_type,
  issuer_url,
  client_id,
  client_secret,
  scope,
  display_order,
  is_enabled,
  created_at
) VALUES (
  'okta_prod',
  'Okta',
  'oidc',
  'https://dev-12345678.okta.com',
  'okta-client-id-here',
  'okta-secret-here',
  'openid profile email groups',
  2,
  1,
  datetime('now')
);
EOF
```

#### Step 3: Optional—Custom Claims for Groups

If you use Okta's custom claims (e.g., `groups`), ensure:
1. The app has the **groups** claim in its token
2. Users are assigned to groups in Okta
3. See [Role Mapping](#role-mapping) to map Okta groups to Graphēon roles

---

### 3. Google

#### Step 1: Create OAuth 2.0 Credentials in Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
4. Choose **Web application**
5. Add Authorized Redirect URIs:
   - `https://your-domain.com/auth/callback`
   - `http://localhost:8000/auth/callback` (for development)
6. Save. Note the **Client ID** and **Client Secret**

#### Step 2: Register Provider in Graphēon

Google is a standard OIDC provider. Use `https://accounts.google.com` as the issuer:

```bash
sqlite3 /app/data/network.db << 'EOF'
INSERT INTO auth_providers (
  provider_name,
  display_name,
  provider_type,
  issuer_url,
  client_id,
  client_secret,
  scope,
  display_order,
  is_enabled,
  created_at
) VALUES (
  'google',
  'Google',
  'oidc',
  'https://accounts.google.com',
  'your-google-client-id.apps.googleusercontent.com',
  'your-google-client-secret',
  'openid profile email',
  3,
  1,
  datetime('now')
);
EOF
```

#### Step 3: Notes

- Google does not return a `groups` claim by default
- For group-based role mapping, you would need to use Google Workspace Directory API or custom attributes
- Most deployments map on `email` domain (e.g., all `@example.com` → editor)

---

### 4. GitHub

#### Step 1: Register OAuth App in GitHub

1. Go to GitHub Settings → **Developer settings** → **OAuth Apps** → **New OAuth App**
2. Fill in:
   - **Application name:** `Grapheon`
   - **Homepage URL:** `https://your-domain.com`
   - **Authorization callback URL:** `https://your-domain.com/auth/callback`
3. Save. Note the **Client ID** and generate a **Client Secret**

#### Step 2: Register Provider in Graphēon

GitHub should be configured as an OAuth2 provider with explicit endpoints:

```bash
sqlite3 /app/data/network.db << 'EOF'
INSERT INTO auth_providers (
  provider_name,
  display_name,
  provider_type,
  issuer_url,
  client_id,
  client_secret,
  scope,
  authorization_endpoint,
  token_endpoint,
  userinfo_endpoint,
  display_order,
  is_enabled,
  created_at
) VALUES (
  'github',
  'GitHub',
  'oauth2',
  'https://github.com',
  'your-github-client-id',
  'your-github-client-secret',
  'read:user user:email',
  'https://github.com/login/oauth/authorize',
  'https://github.com/login/oauth/access_token',
  'https://api.github.com/user',
  4,
  1,
  datetime('now')
);
EOF
```

#### Step 3: GitHub Role Mapping Notes

For role mapping, use claims returned by `/user` (for example `preferred_username` or `email`). Organization/team-based mapping requires additional enrichment beyond the default userinfo call.

---

### 5. GitLab

#### Step 1: Create OAuth Application in GitLab

1. Log in to your GitLab instance
2. **User settings** → **Applications** → **New application**
3. Fill in:
   - **Name:** `Grapheon`
   - **Redirect URI:** `https://your-domain.com/auth/callback`
   - **Scopes:** `openid`, `profile`, `email`, `read_user` (select as needed)
4. Save. Note the **Application ID** (client_id) and **Secret**

#### Step 2: Register Provider in Graphēon

```bash
sqlite3 /app/data/network.db << 'EOF'
INSERT INTO auth_providers (
  provider_name,
  display_name,
  provider_type,
  issuer_url,
  client_id,
  client_secret,
  scope,
  display_order,
  is_enabled,
  created_at
) VALUES (
  'gitlab_prod',
  'GitLab',
  'oidc',
  'https://gitlab.example.com',
  'your-gitlab-app-id',
  'your-gitlab-secret',
  'openid profile email read_user',
  5,
  1,
  datetime('now')
);
EOF
```

Replace `https://gitlab.example.com` with your GitLab instance URL (use `https://gitlab.com` for GitLab.com).

#### Step 3: GitLab Groups & Membership

GitLab includes group membership in the token. See [Role Mapping](#role-mapping) for mapping groups to roles.

---

## Role Mapping

Role mappings define how IdP claims (e.g., group memberships) are converted to Graphēon roles. Mappings are stored in the `role_mappings` table.

### Basic Concepts

- **idp_claim_path:** Dot-notation path to a claim in the ID token (e.g., `groups`, `resource_access.app.roles`)
- **idp_claim_value:** The value (or list item) that triggers the role assignment
- **app_role:** The target role in Graphēon (`admin`, `editor`, or `viewer`)
- **Priority:** If multiple mappings match, the highest-privilege role is assigned (admin > editor > viewer)

### Table Structure

| Column | Type | Example |
|--------|------|---------|
| `id` | Integer | (auto) |
| `provider_id` | Integer | FK to `auth_providers.id` |
| `idp_claim_path` | String | `groups` |
| `idp_claim_value` | String | `grapheon-admins` |
| `app_role` | String | `admin` |
| `is_enabled` | Integer | `1` |
| `created_at` | Timestamp | (auto) |

### Matching Logic

When a user logs in:
1. For each enabled mapping for that provider:
   - Look up the claim at `idp_claim_path` in the user's token
   - If the claim is a list and contains `idp_claim_value`, the mapping matches
   - If the claim equals `idp_claim_value`, the mapping matches
2. Collect all matching mappings
3. Assign the highest-privilege role: admin > editor > viewer
4. If no mappings match, assign the default role: `viewer`

### Example: Authentik with Groups

**Scenario:**
- Authentik sends a `groups` claim with a list: `["grapheon-admins", "network-team"]`
- You want to map:
  - `grapheon-admins` → admin
  - `grapheon-editors` → editor
  - `network-team` → viewer

First, find the provider ID:

```bash
sqlite3 /app/data/network.db
SQLite version 3.x.x
sqlite> SELECT id, provider_name FROM auth_providers WHERE provider_name = 'authentik_prod';
1|authentik_prod
```

Then insert the mappings:

```bash
sqlite3 /app/data/network.db << 'EOF'
INSERT INTO role_mappings (provider_id, idp_claim_path, idp_claim_value, app_role, is_enabled, created_at) VALUES
  (1, 'groups', 'grapheon-admins', 'admin', 1, datetime('now')),
  (1, 'groups', 'grapheon-editors', 'editor', 1, datetime('now')),
  (1, 'groups', 'network-team', 'viewer', 1, datetime('now'));
EOF
```

**User login flow:**
- User with groups `["grapheon-admins", "network-team"]` logs in
- Mappings match: admin, viewer
- Assigned role: **admin** (highest privilege)

---

### Example: Okta with Custom Claims

**Scenario:**
- Okta sends a custom claim `app_roles` with list: `["okta-admins"]`
- You want to map:
  - `okta-admins` → admin
  - `okta-readers` → viewer

Find the Okta provider:

```bash
sqlite3 /app/data/network.db
sqlite> SELECT id, provider_name FROM auth_providers WHERE provider_name = 'okta_prod';
2|okta_prod
```

Insert mappings:

```bash
sqlite3 /app/data/network.db << 'EOF'
INSERT INTO role_mappings (provider_id, idp_claim_path, idp_claim_value, app_role, is_enabled, created_at) VALUES
  (2, 'app_roles', 'okta-admins', 'admin', 1, datetime('now')),
  (2, 'app_roles', 'okta-readers', 'viewer', 1, datetime('now'));
EOF
```

---

### Example: Google with Email Domain

**Scenario:**
- Google returns the user's `email`
- You want to map:
  - `admin@example.com` → admin
  - Any `@example.com` → editor
  - Everyone else → viewer (default)

Find the Google provider:

```bash
sqlite3 /app/data/network.db
sqlite> SELECT id, provider_name FROM auth_providers WHERE provider_name = 'google';
3|google
```

Insert mappings:

```bash
sqlite3 /app/data/network.db << 'EOF'
INSERT INTO role_mappings (provider_id, idp_claim_path, idp_claim_value, app_role, is_enabled, created_at) VALUES
  (3, 'email', 'admin@example.com', 'admin', 1, datetime('now')),
  (3, 'email', 'editor@example.com', 'editor', 1, datetime('now'));
EOF
```

**Notes:**
- Email domain matching is not built-in; you would need a mapping per email
- For domain-based rules, use a provider with group claims (Okta, Authentik, GitLab)

---

### Example: GitHub with Organizations

**Scenario:**
- GitHub returns organization memberships (requires `read:org` scope)
- You want to map:
  - Members of `github-org/admins` team → admin
  - Members of `github-org/editors` team → editor

Find the GitHub provider:

```bash
sqlite3 /app/data/network.db
sqlite> SELECT id, provider_name FROM auth_providers WHERE provider_name = 'github';
4|github
```

Insert mappings:

```bash
sqlite3 /app/data/network.db << 'EOF'
INSERT INTO role_mappings (provider_id, idp_claim_path, idp_claim_value, app_role, is_enabled, created_at) VALUES
  (4, 'org_memberships', 'github-org/admins', 'admin', 1, datetime('now')),
  (4, 'org_memberships', 'github-org/editors', 'editor', 1, datetime('now'));
EOF
```

---

### Example: GitLab with Groups

**Scenario:**
- GitLab sends a `groups` claim with list: `["gitlab-group/admins"]`
- You want to map group membership to roles

Find the GitLab provider:

```bash
sqlite3 /app/data/network.db
sqlite> SELECT id, provider_name FROM auth_providers WHERE provider_name = 'gitlab_prod';
5|gitlab_prod
```

Insert mappings:

```bash
sqlite3 /app/data/network.db << 'EOF'
INSERT INTO role_mappings (provider_id, idp_claim_path, idp_claim_value, app_role, is_enabled, created_at) VALUES
  (5, 'groups', 'gitlab-group/admins', 'admin', 1, datetime('now')),
  (5, 'groups', 'gitlab-group/editors', 'editor', 1, datetime('now'));
EOF
```

---

### Disabling a Mapping

To temporarily disable a mapping without deleting it:

```bash
sqlite3 /app/data/network.db
sqlite> UPDATE role_mappings SET is_enabled = 0 WHERE id = 1;
```

---

## Docker / Container Setup

### Basic Docker Run

```bash
docker run -d \
  --name grapheon \
  -p 8000:8000 \
  -v grapheon-db:/app/data \
  -e AUTH_ENABLED=True \
  -e ENFORCE_AUTH=True \
  -e JWT_SECRET="your-secret-key-at-least-32-characters" \
  -e JWT_ALGORITHM="HS256" \
  -e JWT_EXPIRATION_MINUTES="60" \
  -e LOCAL_ADMIN_USERNAME="admin" \
  -e LOCAL_ADMIN_EMAIL="admin@example.com" \
  -e LOCAL_ADMIN_PASSWORD="AdminPassword123!" \
  grapheon:latest
```

### Docker Compose Example

```yaml
version: '3.8'

services:
  grapheon:
    image: grapheon:latest
    container_name: grapheon
    ports:
      - "8000:8000"
    volumes:
      - grapheon-db:/app/data
    environment:
      # Auth Feature Flags
      AUTH_ENABLED: "True"
      ENFORCE_AUTH: "True"

      # JWT Configuration
      JWT_SECRET: "your-production-secret-key-min-32-chars"
      JWT_ALGORITHM: "HS256"
      JWT_EXPIRATION_MINUTES: "60"

      # Local Admin Bootstrap
      LOCAL_ADMIN_USERNAME: "admin"
      LOCAL_ADMIN_EMAIL: "admin@example.com"
      LOCAL_ADMIN_PASSWORD: "AdminPassword123!"

      # Optional: Application Settings
      LOG_LEVEL: "INFO"
      WORKERS: "4"

    restart: unless-stopped

  # Optional: SQLite browser for debugging
  adminer:
    image: adminer
    container_name: grapheon-adminer
    ports:
      - "8081:8080"
    environment:
      ADMINER_DEFAULT_SERVER: "grapheon"
    depends_on:
      - grapheon
    restart: unless-stopped

volumes:
  grapheon-db:
    driver: local
```

Save as `docker-compose.yml` and run:

```bash
docker-compose up -d
```

Access:
- **Graphēon:** `http://localhost:8000`
- **SQLite Browser (Adminer):** `http://localhost:8081` (optional)

### Production Notes

- **JWT_SECRET:** Generate a strong random key:
  ```bash
  openssl rand -base64 32
  ```
- **Database persistence:** Always mount the `/app/data` volume to avoid losing user data
- **HTTPS:** Use a reverse proxy (nginx, Traefik) to enforce HTTPS in production
- **Token expiration:** Adjust `JWT_EXPIRATION_MINUTES` based on your security policy (60 min is reasonable)

---

## Systemd / Podman Setup

Current host deployments run Podman containers managed by systemd services (not Quadlet-specific units).

- Expected service names:
  - `grapheon-backend.service`
  - `grapheon-frontend.service` (optional when frontend is hosted on Cloudflare Pages)
- Persistent backend data should be mounted to `/app/data`.
- For complete NixOS + Podman + systemd examples (including upgrade automation), use:
  - `docs/example_deployment.md`

Authentication-specific production defaults remain:

- Set `ENFORCE_AUTH=True`
- Set a strong `JWT_SECRET`
- Configure local admin bootstrap and/or OIDC providers before enforcing auth

---

## API Reference

All auth endpoints accept and return JSON. Authentication is via the `Authorization: Bearer <JWT>` header.

### Public Endpoints

#### GET /api/auth/providers

Lists all enabled OIDC providers and whether local auth is enabled.

**Request:**
```http
GET /api/auth/providers
```

**Response:**
```json
{
  "providers": [
    {
      "provider_name": "authentik_prod",
      "display_name": "Authentik (Corporate)",
      "provider_type": "oidc",
      "display_order": 1,
      "issuer_url": "https://auth.example.com"
    },
    {
      "provider_name": "okta_prod",
      "display_name": "Okta",
      "provider_type": "oidc",
      "display_order": 2,
      "issuer_url": "https://dev-12345678.okta.com"
    }
  ],
  "local_auth_enabled": true
}
```

---

#### POST /api/auth/callback

Exchange OIDC authorization code for a JWT token. Called by the frontend after redirect from the IdP.

**Request:**
```json
{
  "code": "AUTH_CODE_FROM_IDP",
  "provider": "authentik_prod",
  "redirect_uri": "https://your-domain.com/auth/callback",
  "code_verifier": "PKCE_CODE_VERIFIER"
}
```

**Response (Success):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Response (Error):**
```json
{
  "detail": "Invalid authorization code"
}
```

Status: `400`, `401`, or `500` on failure.

---

#### POST /api/auth/login/local

Authenticate with username and password (local auth only).

**Request:**
```json
{
  "username": "admin",
  "password": "YourPassword"
}
```

**Response (Success):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Response (Error):**
```json
{
  "detail": "Invalid credentials"
}
```

Status: `401` on failure.

---

### Authenticated Endpoints

All authenticated endpoints require the `Authorization: Bearer <JWT>` header.

#### GET /api/auth/me

Return the current authenticated user's profile.

**Request:**
```http
GET /api/auth/me
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

**Response:**
```json
{
  "id": "user-uuid-here",
  "username": "john.doe",
  "email": "john.doe@example.com",
  "role": "editor",
  "provider": "authentik_prod",
  "last_login": "2025-02-07T14:30:00Z"
}
```

Status: `401` if token is invalid or expired.

---

#### POST /api/auth/logout

Invalidate the current session (audit only; JWT is stateless).

**Request:**
```http
POST /api/auth/logout
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

**Response:**
```json
{
  "message": "Logout recorded"
}
```

Status: `200` on success. The frontend should delete the token from localStorage.

---

### Admin-Only Endpoints

All admin endpoints require `role = admin`.

#### GET /api/auth/users

List all users in the system.

**Request:**
```http
GET /api/auth/users
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

**Response:**
```json
{
  "users": [
    {
      "id": "user-1",
      "username": "admin",
      "email": "admin@example.com",
      "role": "admin",
      "provider": "local",
      "created_at": "2025-02-01T10:00:00Z",
      "last_login": "2025-02-07T14:30:00Z"
    },
    {
      "id": "user-2",
      "username": "john.doe",
      "email": "john.doe@example.com",
      "role": "editor",
      "provider": "authentik_prod",
      "created_at": "2025-02-02T11:00:00Z",
      "last_login": "2025-02-07T13:15:00Z"
    }
  ]
}
```

Status: `403` if not admin.

---

#### PATCH /api/auth/users/{id}/role

Change a user's role. Admin only.

**Request:**
```json
{
  "role": "viewer"
}
```

**Response:**
```json
{
  "id": "user-2",
  "username": "john.doe",
  "email": "john.doe@example.com",
  "role": "viewer",
  "provider": "authentik_prod"
}
```

Status: `404` if user not found, `403` if not admin.

---

## Troubleshooting

### Issue: Login Page Shows "No Providers Available"

**Symptoms:**
- Users see the login form but no provider buttons
- Only local login (if enabled) is available

**Causes:**
1. No OIDC providers are registered in the database
2. All providers are disabled (`is_enabled = 0`)
3. `LOCAL_ADMIN_USERNAME` is not set (local auth won't be available either)

**Solution:**
1. Check the providers table:
   ```bash
   sqlite3 /app/data/network.db "SELECT provider_name, display_name, is_enabled FROM auth_providers;"
   ```
2. Verify at least one provider has `is_enabled = 1`
3. If no providers exist, insert one using the steps in [Configuring OIDC Providers](#configuring-oidc-providers)
4. Restart the application for changes to take effect

---

### Issue: "Invalid Redirect URI" Error During OIDC Login

**Symptoms:**
- User clicks a provider button
- IdP redirects back with error: "Redirect URI mismatch" or "Invalid redirect_uri"

**Causes:**
1. The redirect URI in the IdP OAuth app registration doesn't match the one configured in Graphēon
2. HTTPS/HTTP protocol mismatch (e.g., IdP expects HTTPS but app uses HTTP)
3. Port mismatch or domain name mismatch

**Solution:**
1. Determine the correct redirect URI for your deployment:
   - **Local development:** `http://localhost:8000/auth/callback`
   - **Production with domain:** `https://your-domain.com/auth/callback`
2. Update the OAuth app in your IdP with the exact URI
3. **Authentik:** Applications → Your App → Protocol Settings → Redirect URI
4. **Okta:** Applications → Your App → General → Redirect URIs
5. **Google:** APIs & Services → Credentials → Edit → Authorized redirect URIs
6. **GitHub:** Settings → Developer settings → OAuth Apps → Edit
7. **GitLab:** User settings → Applications → Edit
8. Restart Graphēon or wait for cache refresh (typically < 1 minute)

---

### Issue: "Clock Skew" or Token Validation Failures

**Symptoms:**
- OIDC login works initially but fails intermittently
- Logs show: "Token validation failed" or "Claims verification failed"
- Error occurs more frequently under certain conditions

**Causes:**
1. System clock is out of sync (JWT expiration is time-based)
2. IdP and Graphēon server times differ by more than 5 minutes
3. Token algorithm or signature mismatch

**Solution:**
1. Synchronize system clocks on both IdP and Graphēon servers:
   ```bash
   sudo timedatectl set-ntp true
   timedatectl status
   ```
2. Use an NTP server for continuous sync:
   ```bash
   sudo apt-get install ntp
   sudo systemctl start ntp
   ```
3. If running in containers, ensure the host system time is correct (check your hypervisor/cloud provider settings)

---

### Issue: "Invalid JWT Secret" or Token Signing Errors

**Symptoms:**
- Users can log in successfully initially
- After a restart, existing tokens are invalid
- All users are logged out

**Causes:**
1. `JWT_SECRET` environment variable is not set on restart
2. `JWT_SECRET` was changed between restarts
3. `JWT_ALGORITHM` was changed

**Solution:**
1. Set a persistent `JWT_SECRET` that doesn't change between restarts:
   ```bash
   export JWT_SECRET="your-secret-key-at-least-32-characters"
   ```
2. Store it in your `.env` file or container configuration:
   ```bash
   # .env
   JWT_SECRET=your-secret-key-at-least-32-characters
   JWT_ALGORITHM=HS256
   JWT_EXPIRATION_MINUTES=60
   ```
3. Never change `JWT_SECRET` or `JWT_ALGORITHM` after deployment without invalidating all existing tokens
4. (Future) Implement token blacklist in Redis for forced invalidation

---

### Issue: OIDC Discovery Fails ("Cannot fetch .well-known")

**Symptoms:**
- Provider registration succeeds, but provider doesn't appear on login page
- Logs show: "Failed to fetch OIDC discovery endpoint"
- Network requests to IdP are timing out

**Causes:**
1. Issuer URL is incorrect
2. IdP's `.well-known/openid-configuration` endpoint is not publicly accessible
3. Network firewall blocks outbound requests
4. IdP requires authentication to access the discovery endpoint (unusual)

**Solution:**
1. Verify the issuer URL is correct:
   - **Authentik:** `https://auth.example.com` (no `/application/o/` path)
   - **Keycloak:** `https://keycloak.example.com/auth/realms/your-realm`
   - **Okta:** `https://your-domain.okta.com`
   - **Google:** `https://accounts.google.com`
   - **GitHub:** `https://github.com`
   - **GitLab:** `https://gitlab.example.com` or `https://gitlab.com`

2. Test the discovery endpoint manually:
   ```bash
   curl https://auth.example.com/.well-known/openid-configuration
   ```
   Should return JSON with `authorization_endpoint`, `token_endpoint`, etc.

3. If the endpoint is accessible but Graphēon still fails:
   - Check firewall rules on your network
   - Verify Graphēon container has outbound HTTPS access
   - Check IdP logs for 403 Forbidden responses

4. If manual endpoints are known, you can specify them explicitly:
   ```bash
   sqlite3 /app/data/network.db << 'EOF'
   UPDATE auth_providers SET
     authorization_endpoint = 'https://auth.example.com/application/o/authorize/',
     token_endpoint = 'https://auth.example.com/application/o/token/',
     userinfo_endpoint = 'https://auth.example.com/application/o/userinfo/'
   WHERE provider_name = 'authentik_prod';
   EOF
   ```

---

### Issue: Role Mapping Not Working

**Symptoms:**
- User logs in successfully
- Role is always "viewer" regardless of IdP groups/claims
- Expected mappings don't take effect

**Causes:**
1. Role mappings are not registered or disabled
2. `idp_claim_path` doesn't match actual token claims
3. `idp_claim_value` doesn't match IdP data
4. Mapping is registered for wrong provider

**Solution:**
1. Verify mappings exist and are enabled:
   ```bash
   sqlite3 /app/data/network.db "SELECT id, provider_id, idp_claim_path, idp_claim_value, app_role, is_enabled FROM role_mappings WHERE is_enabled = 1;"
   ```

2. Inspect the user's actual token claims:
   - After login, check browser DevTools → Storage → Cookies
   - Copy the JWT and decode it at [jwt.io](https://jwt.io)
   - Verify the claims match your `idp_claim_path` values

3. Example: If token contains:
   ```json
   {
     "groups": ["network-team", "grapheon-admins"]
   }
   ```
   Then your mapping should use `idp_claim_path = "groups"` and `idp_claim_value = "grapheon-admins"`.

4. Ensure the provider_id in the mapping matches the correct provider:
   ```bash
   sqlite3 /app/data/network.db "SELECT id, provider_name FROM auth_providers;"
   ```

5. Restart Graphēon after updating role mappings

---

### Issue: ENFORCE_AUTH=True but Requests Still Work Without JWT

**Symptoms:**
- `ENFORCE_AUTH` is set to `True`
- API requests without `Authorization` header are still accepted
- Expected 401 errors don't occur

**Causes:**
1. Application not restarted after environment variable change
2. Feature flag logic not applied to all endpoints
3. Endpoint is marked as public

**Solution:**
1. Ensure `ENFORCE_AUTH` is actually set:
   ```bash
   docker exec grapheon printenv | grep ENFORCE_AUTH
   ```
2. Restart the application:
   ```bash
   docker restart grapheon
   ```
   Or if using systemd:
   ```bash
   sudo systemctl restart grapheon
   ```
3. Test an endpoint:
   ```bash
   curl -i http://localhost:8000/api/hosts
   ```
   Should return `401 Unauthorized`

4. If still not working, check logs for startup errors:
   ```bash
   docker logs grapheon 2>&1 | grep -i auth
   ```

---

### Issue: Users Can't Log Out

**Symptoms:**
- Logout endpoint returns 200 OK
- Token remains valid in localStorage
- User can still use the app after logout

**Causes:**
1. Frontend is not deleting the token from localStorage
2. Token expiration time is very long
3. (Known limitation) JWTs are stateless; logout is audit-only

**Solution (Short-term):**
1. Ensure frontend properly clears the token:
   ```javascript
   // After calling POST /api/auth/logout
   localStorage.removeItem('auth_token');
   window.location.href = '/login';
   ```

2. Reduce `JWT_EXPIRATION_MINUTES` to limit token lifetime:
   ```bash
   JWT_EXPIRATION_MINUTES=30
   ```

**Solution (Long-term):**
- (Future) Implement token blacklist using Redis to invalidate tokens on logout

---

## Security Considerations

### 1. Change JWT_SECRET in Production

**Critical:** The default `JWT_SECRET` is not secure. Always generate a strong random key:

```bash
openssl rand -base64 32
```

Then set it in your environment:

```bash
export JWT_SECRET="your-generated-32-char-key"
```

**Do not commit secrets to version control.** Use:
- Container secret management (Docker Secrets, Kubernetes Secrets)
- `.env` files (not committed, loaded at runtime)
- Vault services (HashiCorp Vault, AWS Secrets Manager)

---

### 2. Enforce HTTPS

JWTs and OIDC flows should only run over HTTPS to prevent token interception.

**In production, use a reverse proxy:**

**nginx example:**
```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

**Traefik example:**
```yaml
services:
  grapheon:
    image: grapheon:latest
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.grapheon.rule=Host(`your-domain.com`)"
      - "traefik.http.routers.grapheon.entrypoints=websecure"
      - "traefik.http.routers.grapheon.tls.certresolver=letsencrypt"
      - "traefik.http.services.grapheon.loadbalancer.server.port=8000"

  traefik:
    image: traefik:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./letsencrypt:/letsencrypt
    command:
      - "--api.insecure=true"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web"
      - "--certificatesresolvers.letsencrypt.acme.email=admin@example.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=letsencrypt/acme.json"
```

---

### 3. Token Expiration

Shorter token lifetimes reduce the impact of token theft:

- **Development:** 120–360 minutes (allow testing without frequent re-login)
- **Staging:** 60 minutes
- **Production:** 15–60 minutes (balance security and UX)

Set via `JWT_EXPIRATION_MINUTES`:

```bash
JWT_EXPIRATION_MINUTES=30
```

Users will need to re-authenticate after expiration. The frontend should detect 401 responses and redirect to login.

---

### 4. PKCE for OIDC

All OIDC flows should use PKCE (Proof Key for Code Exchange) to prevent authorization code interception. The frontend implementation includes PKCE; ensure it's always enabled.

**PKCE flow:**
1. Frontend generates `code_verifier` (random 43–128 character string)
2. Frontend computes `code_challenge = base64url(sha256(code_verifier))`
3. Frontend includes `code_challenge` in authorization request
4. After IdP redirects, frontend includes `code_verifier` in token exchange
5. Backend validates: `sha256(code_verifier) == code_challenge`

This prevents attackers from using intercepted authorization codes.

---

### 5. No Server-Side Token Invalidation (Current Limitation)

**Known limitation:** JWTs are stateless. Logout, role changes, and revocation are not immediately enforced on existing tokens.

**Workarounds:**
1. Shorter token lifetimes (users re-authenticate frequently)
2. Respect token expiration on the frontend; don't auto-refresh indefinitely
3. (Future) Implement Redis-backed token blacklist for immediate invalidation

**If immediate revocation is required:**
- Roll out a manual token rotation: inform users to clear localStorage and log back in
- Implement a blacklist service (roadmap for v0.9.0+)

---

### 6. Database Security

The SQLite database contains user credentials (hashed passwords) and OIDC secrets.

**Protect the database:**
1. **File permissions:**
   ```bash
   chmod 600 /app/data/network.db
   ```
2. **Backup encryption:**
   ```bash
   sqlite3 /app/data/network.db ".backup | gzip | openssl enc -aes-256-cbc -out backup.db.gz.enc"
   ```
3. **Access control:** Only Graphēon process should read the database
4. **Audit logging:** Monitor database file modifications:
   ```bash
   auditctl -w /app/data/network.db -p wa -k grapheon_db
   ```

---

### 7. OIDC Provider Secrets

Client secrets for OIDC providers are stored in the database (plaintext, encrypted with local key in future versions).

**Best practices:**
1. Use strong, unique secrets: `openssl rand -base64 32`
2. Rotate provider secrets periodically (requires IdP and database update)
3. Use different secrets per environment (dev, staging, prod)
4. Never commit secrets to version control

---

### 8. Audit Logging

All authentication events should be logged for compliance:
- Successful login (user, provider, timestamp)
- Failed login attempts (username, provider, timestamp, reason)
- Logout (user, timestamp)
- Role changes (admin, affected user, old role, new role, timestamp)
- Provider configuration changes

(Log-to-syslog integration is planned for v0.9.0+)

---

### 9. Monitor 401 Unauthorized Responses

A spike in 401 errors may indicate:
- Token validation failures (clock skew, secret mismatch)
- OIDC provider outage
- Attacker attempting token forgery

**Set up alerts:**
```bash
# Example: Alert if 401 rate > 10 per minute
docker logs grapheon 2>&1 | grep "401" | wc -l
```

---

### 10. Future Security Enhancements

Planned for upcoming releases:
- Token blacklist (Redis) for immediate revocation
- Rate limiting on login endpoints
- MFA support
- OAuth2 client credentials flow for service accounts
- Encrypted secret storage (age or similar)

---

## Appendix: Common OIDC Claim Paths by Provider

| Provider | Claim Path | Example Value |
|----------|-----------|----------------|
| **Authentik** | `groups` | `["grapheon-admins"]` |
| **Keycloak** | `realm_access.roles` or `resource_access.{client_id}.roles` | `["admin"]` |
| **Okta** | `groups` (custom claim) | `["okta-admins"]` |
| **Google** | `email` | `admin@example.com` |
| **GitHub** | `org_memberships` (requires read:org) | `["github-org/admins"]` |
| **GitLab** | `groups` | `["gitlab-group/admins"]` |

Consult your IdP's OIDC documentation to confirm custom claim names.

---

## Support & Further Reading

- **OIDC Specification:** [openid.net](https://openid.net/specs/openid-connect-core-1_0.html)
- **PKCE (RFC 7636):** [tools.ietf.org](https://tools.ietf.org/html/rfc7636)
- **JWT (RFC 7519):** [tools.ietf.org](https://tools.ietf.org/html/rfc7519)
- **Graphēon GitHub:** [github.com/your-org/grapheon](https://github.com/your-org/grapheon)

For issues or questions, open an issue on GitHub or contact the maintainers.

---

**End of Authentication Provider Setup Guide**
