from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re
from collections.abc import Mapping

from fastapi import HTTPException, Request, status

from local_agent.app.config import AppConfig


AUTH_TOKEN_HEADER = "X-Local-Agent-Token"
AUTH_USER_HEADER = "X-Local-Agent-User"
AUTH_SESSION_HEADER = "X-Local-Agent-Session"


@dataclass(frozen=True, slots=True)
class AuthIdentity:
    enabled: bool
    authenticated: bool
    user_id: str
    requested_session_id: str
    session_id: str
    auth_mode: str = "disabled"


def authenticate_request(request: Request, config: AppConfig) -> AuthIdentity:
    return authenticate_headers(request.headers, config)


def authenticate_headers(headers: Mapping[str, str], config: AppConfig) -> AuthIdentity:
    if not config.auth_enabled:
        session_id = sanitize_session_id(headers.get(AUTH_SESSION_HEADER), fallback="default")
        return AuthIdentity(
            enabled=False,
            authenticated=False,
            user_id=sanitize_user_id(headers.get(AUTH_USER_HEADER), fallback="local"),
            requested_session_id=session_id,
            session_id=session_id,
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

    fallback_user = f"user-{_token_fingerprint(expected_token)}"
    user_id = sanitize_user_id(headers.get(AUTH_USER_HEADER), fallback=fallback_user)
    requested_session_id = sanitize_session_id(headers.get(AUTH_SESSION_HEADER), fallback="default")
    return AuthIdentity(
        enabled=True,
        authenticated=True,
        user_id=user_id,
        requested_session_id=requested_session_id,
        session_id=namespaced_session_id(user_id, requested_session_id),
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


def sanitize_user_id(value: str | None, *, fallback: str = "local") -> str:
    raw = (value or "").strip()
    if not raw:
        return fallback
    normalized = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", raw)
    normalized = normalized.strip("-_.:")
    if not normalized:
        return fallback
    return normalized[:48]


def namespaced_session_id(user_id: str, session_id: str) -> str:
    normalized_user = sanitize_user_id(user_id)
    normalized_session = sanitize_session_id(session_id, fallback="default")
    return sanitize_session_id(f"{normalized_user}:{normalized_session}", fallback=normalized_user)


def _extract_token(headers: Mapping[str, str]) -> str:
    bearer = headers.get("Authorization") or ""
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()
    return (headers.get(AUTH_TOKEN_HEADER) or "").strip()


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
