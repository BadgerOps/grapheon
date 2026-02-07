"""
Attribute-Based Access Control (ABAC) — future expansion stubs.

This module provides placeholder functions for a future ABAC policy engine.
Currently, Grapheon uses simple 3-tier RBAC (admin/editor/viewer).

When ABAC is needed, consider:
- **Casbin** (``pycasbin``) — mature policy engine with ABAC support,
  SQLAlchemy adapter for persistent policies, FastAPI integration.
- **OPA** (Open Policy Agent) — sidecar service for complex policies.

ABAC would add:
- Per-subnet access control (user X can view 10.0.0.0/8 but not 192.168.x.x)
- Per-VLAN management (user Y can manage VLAN 10 but not VLAN 100)
- Department-based data visibility
- Time-based access windows
- Export restrictions based on data sensitivity

The ``User.user_metadata`` JSON column is already reserved for ABAC attributes.

Example future usage::

    from auth.abac_stubs import can_access

    @router.get("/hosts/{host_id}")
    async def get_host(
        host_id: int,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        host = await fetch_host(db, host_id)
        if not await can_access(user, "host", host_id, "read"):
            raise HTTPException(403, "ABAC policy denied access")
        return host
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def can_access(
    user: Any,
    resource_type: str,
    resource_id: Optional[int] = None,
    action: str = "read",
) -> bool:
    """
    Evaluate whether a user can perform an action on a resource.

    **Stub** — always returns ``True``. Replace with Casbin or OPA
    integration when ABAC is implemented.

    Args:
        user: User model instance.
        resource_type: Type of resource (``"host"``, ``"subnet"``, ``"vlan"``).
        resource_id: Optional specific resource ID.
        action: Action to perform (``"read"``, ``"write"``, ``"delete"``,
            ``"export"``).

    Returns:
        ``True`` if access is allowed.
    """
    # TODO: Implement ABAC policy evaluation
    # Example with Casbin:
    #   enforcer = casbin.Enforcer("model.conf", adapter)
    #   return enforcer.enforce(user.username, resource_type, action)
    return True


async def can_access_subnet(user: Any, subnet_cidr: str) -> bool:
    """
    Check if user can access hosts in a specific subnet.

    **Stub** — always returns ``True``.
    """
    # TODO: Check user.user_metadata["allowed_subnets"] against subnet_cidr
    return True


async def can_export(user: Any, export_format: str) -> bool:
    """
    Check if user can export data in a specific format.

    **Stub** — always returns ``True``.
    """
    # TODO: Check export restrictions based on user attributes
    return True
