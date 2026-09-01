"""
API key authentication with role-based access control (RBAC).

Roles are hierarchical: admin > analyst > viewer. Each configured API key
maps to exactly one role (see `Settings.api_key_roles`). Endpoints declare
the minimum role they require via `require_role(min_role)`.

Real production auth would be OAuth2/JWT backed by a user database with
per-tenant scoping, key rotation, and a proper roles table. For a
single-service portfolio deployment, a static API-key-to-role allowlist
(checked via constant-time comparison to avoid timing attacks) is the
right-sized choice - it demonstrates the RBAC *pattern* without building
a full identity provider integration this project doesn't need to prove
the point.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from ..config import settings

ROLE_HIERARCHY = {"viewer": 0, "analyst": 1, "admin": 2}


def _constant_time_lookup(candidate: str, roles: dict) -> str | None:
    """Constant-time-compare `candidate` against every known key, returning
    the matched key's role (or None). Iterates all keys rather than dict
    lookup so timing doesn't leak which prefix of a key is correct."""
    matched_role = None
    for key, role in roles.items():
        if hmac.compare_digest(candidate, key):
            matched_role = role
    return matched_role


async def require_api_key(x_api_key: str = Header(default="")) -> str:
    """Backward-compatible dependency: any valid key, any role."""
    role = _constant_time_lookup(x_api_key, settings.api_key_roles) if x_api_key else None
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key. Pass a valid key in the X-API-Key header.",
        )
    return x_api_key


def require_role(min_role: str):
    """
    Dependency factory: returns a FastAPI dependency that requires the
    caller's API key to map to `min_role` or higher in the hierarchy.

    Usage: `Depends(require_role("admin"))`
    """
    if min_role not in ROLE_HIERARCHY:
        raise ValueError(f"Unknown role: {min_role!r}")

    async def _check(x_api_key: str = Header(default="")) -> str:
        role = _constant_time_lookup(x_api_key, settings.api_key_roles) if x_api_key else None
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid API key.",
            )
        if ROLE_HIERARCHY[role] < ROLE_HIERARCHY[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This endpoint requires '{min_role}' role or higher; your key has '{role}'.",
            )
        return x_api_key

    return _check
