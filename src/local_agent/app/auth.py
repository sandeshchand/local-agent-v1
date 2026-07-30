from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re
from collections.abc import Mapping

from fastapi import HTTPException, Request, status

from local_agent.app.config import AppConfig


AUTH_TOKEN_HEADER = "X-Local-Agent-Token"
AUTH_SESSION_HEADER = "X-Local-Agent-Session"


@dataclass(frozen=True, slots=True)
class AuthIdentity:
    enabled: bool
    authenticated: bool
    session_id: str
    auth_mode: str = "disabled"


def authenticate_request(request: Request, config: AppConfig) -> AuthIdentity:
    return authenticate_headers(request.headers, config)


def authenticate_headers(headers: Mapping[str, str], config: AppConfig) -> AuthIdentity:
    if not config.auth_enabled:
        return AuthIdentity(
            enabled=False,
            authenticated=False,
            session_id=sanitize_session_id(headers.get(AUTH_SESSION_HEADER), fallback="default"),
        )

    expected_token = config.auth_token.strip()
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is enabled but AUTH_TOKEN is not configured.",
        )

    provided_token = _extract_token(headers)
    if not provided_token or not hmac.compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    fallback_session = f"user-{_token_fingerprint(expected_token)}"
    return AuthIdentity(
        enabled=True,
        authenticated=True,
        session_id=sanitize_session_id(headers.get(AUTH_SESSION_HEADER), fallback=fallback_session),
        auth_mode="api_token",
    )


def sanitize_session_id(value: str | None, *, fallback: str = "default") -> str:
    raw = (value or "").strip()
    if not raw:
        return fallback
    normalized = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", raw)
    normalized = normalized.strip("-_.:")
    if not normalized:
        return fallback
    return normalized[:80]


def _extract_token(headers: Mapping[str, str]) -> str:
    bearer = headers.get("Authorization") or ""
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()
    return (headers.get(AUTH_TOKEN_HEADER) or "").strip()


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
