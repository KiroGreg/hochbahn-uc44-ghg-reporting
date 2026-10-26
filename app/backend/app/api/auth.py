"""Auth endpoints.

`/api/auth/check` is the only call the frontend needs: it triggers the
bearer-token dependency, which 401s on bad/missing tokens. A 200 means
the token in localStorage is still valid.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.auth import auth_enabled, require_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get(
    "/check",
    summary="Validate the bearer token; returns 200 on success, 401 otherwise.",
    dependencies=[Depends(require_token)],
)
def check() -> dict:
    return {"ok": True, "auth_enabled": auth_enabled()}


@router.get(
    "/status",
    summary="Whether the server requires authentication (no token needed).",
)
def status() -> dict:
    return {"auth_enabled": auth_enabled()}
