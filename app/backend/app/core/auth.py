"""Shared-token bearer auth.

A single shared secret in `UC44_AUTH_TOKEN`. Every request to `/api/*`
must carry `Authorization: Bearer <token>` matching that value;
otherwise the dependency raises 401.

This is intentionally simple — it's the trivial gate the use case
asks for, not a real identity system. Rotate the token by restarting
the backend with a new env var.

If `UC44_AUTH_TOKEN` is unset (typical for local dev), auth is
disabled and the dependency is a no-op. Set the env var on any
deployed instance.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request, status


def _expected_token() -> str | None:
    token = os.getenv("UC44_AUTH_TOKEN")
    if token is None:
        return None
    token = token.strip()
    return token or None


def require_token(request: Request) -> None:
    expected = _expected_token()
    if expected is None:
        # Auth disabled (no token configured) — local dev mode.
        return

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    provided = auth.split(None, 1)[1].strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def auth_enabled() -> bool:
    return _expected_token() is not None
