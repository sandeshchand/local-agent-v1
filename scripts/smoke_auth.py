from __future__ import annotations

import os
import json
import tempfile
from pathlib import Path

from fastapi import HTTPException

from local_agent.app import web
from local_agent.app.auth import (
    AUTH_SESSION_HEADER,
    AUTH_TOKEN_HEADER,
    AUTH_USER_HEADER,
    AuthIdentity,
    authenticate_headers,
    namespaced_session_id,
    sanitize_session_id,
    sanitize_user_id,
)
from local_agent.app.config import load_config
from local_agent.storage.sqlite_store import SQLiteStore


AUTH_ENV_NAMES = [
    "AUTH_ENABLED",
    "AUTH_TOKEN",
    "QDRANT_PATH",
    "SQLITE_PATH",
    "OLLAMA_BASE_URL",
    "CHAT_MODEL",
    "EMBED_MODEL",
]


def clear_auth_env() -> None:
    for name in AUTH_ENV_NAMES:
        os.environ.pop(name, None)


def write_env(path: Path, *, auth_enabled: bool, auth_token: str = "secret-token") -> None:
    lines = [
        "OLLAMA_BASE_URL=http://127.0.0.1:11434",
        "CHAT_MODEL=test-chat",
        "EMBED_MODEL=test-embed",
        "QDRANT_PATH=./qdrant",
        "SQLITE_PATH=./sqlite/app.db",
        f"AUTH_ENABLED={'true' if auth_enabled else 'false'}",
    ]
    if auth_token:
        lines.append(f"AUTH_TOKEN={auth_token}")
    path.write_text("\n".join(lines), encoding="utf-8")


def assert_auth_headers() -> None:
    assert sanitize_session_id("Team A / Project 1") == "Team-A-Project-1"
    assert sanitize_session_id("   ", fallback="default") == "default"
    assert sanitize_user_id("Team A / Product 1") == "Team-A-Product-1"
    assert namespaced_session_id("team-a", "default") == "team-a:default"

    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env"
        clear_auth_env()
        write_env(env_path, auth_enabled=False)
        config = load_config(env_path)
        identity = authenticate_headers({}, config)
        assert identity.enabled is False
        assert identity.user_id == "local"
        assert identity.requested_session_id == "default"
        assert identity.session_id == "default"
        identity = authenticate_headers(
            {
                AUTH_USER_HEADER: "demo-user",
                AUTH_SESSION_HEADER: "demo-session",
            },
            config,
        )
        assert identity.user_id == "demo-user"
        assert identity.requested_session_id == "demo-session"
        assert identity.session_id == "demo-session"

        clear_auth_env()
        write_env(env_path, auth_enabled=True, auth_token="secret-token")
        config = load_config(env_path)

        for headers in ({}, {AUTH_TOKEN_HEADER: "wrong-token"}):
            try:
                authenticate_headers(headers, config)
            except HTTPException as exc:
                assert exc.status_code == 401
            else:
                raise AssertionError("Missing or wrong API token should fail.")

        identity = authenticate_headers(
            {
                "Authorization": "Bearer secret-token",
                AUTH_USER_HEADER: "team/a",
                AUTH_SESSION_HEADER: "team/session 1",
            },
            config,
        )
        assert identity.enabled is True
        assert identity.authenticated is True
        assert identity.user_id == "team-a"
        assert identity.requested_session_id == "team-session-1"
        assert identity.session_id == "team-a:team-session-1"

        identity = authenticate_headers({AUTH_TOKEN_HEADER: "secret-token"}, config)
        assert identity.user_id.startswith("user-")
        assert identity.requested_session_id == "default"
        assert identity.session_id.startswith(f"{identity.user_id}:")

        user_a = authenticate_headers(
            {
                AUTH_TOKEN_HEADER: "secret-token",
                AUTH_USER_HEADER: "alice",
                AUTH_SESSION_HEADER: "default",
            },
            config,
        )
        user_b = authenticate_headers(
            {
                AUTH_TOKEN_HEADER: "secret-token",
                AUTH_USER_HEADER: "bob",
                AUTH_SESSION_HEADER: "default",
            },
            config,
        )
        assert user_a.requested_session_id == user_b.requested_session_id == "default"
        assert user_a.session_id == "alice:default"
        assert user_b.session_id == "bob:default"
        assert user_a.session_id != user_b.session_id


def assert_session_scoped_storage_filters() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SQLiteStore(Path(tmpdir) / "app.db")
        store.initialize()
        try:
            trace_a = store.insert_trace(
                session_id="session-a",
                query="Question A",
                top_k=3,
                retrieved_json="{}",
                final_answer="Answer A",
            )
            trace_b = store.insert_trace(
                session_id="session-b",
                query="Question B",
                top_k=3,
                retrieved_json="{}",
                final_answer="Answer B",
            )
            store.upsert_answer_feedback(trace_id=trace_a, rating="like")
            store.upsert_answer_feedback(trace_id=trace_b, rating="dislike", issue_type="bad_retrieval")

            traces_a = store.list_traces(session_id="session-a")
            assert [row["trace_id"] for row in traces_a] == [trace_a]
            audit_b = store.list_trace_audit_rows(session_id="session-b")
            assert [row["trace_id"] for row in audit_b] == [trace_b]

            feedback_a = store.list_answer_feedback(session_id="session-a")
            assert [row["trace_id"] for row in feedback_a] == [trace_a]
            summary_a = store.get_answer_feedback_summary(session_id="session-a")
            assert summary_a["total_count"] == 1
            assert summary_a["like_count"] == 1
            assert summary_a["dislike_count"] == 0
        finally:
            store.close()


def assert_eval_candidate_namespace_filtering() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        store = SQLiteStore(tmp_path / "app.db")
        store.initialize()
        candidates_path = tmp_path / "feedback_eval_candidates.json"
        try:
            alice_trace = store.insert_trace(
                session_id="alice:default",
                query="Alice question",
                top_k=3,
                retrieved_json="{}",
                final_answer="Alice answer",
            )
            bob_trace = store.insert_trace(
                session_id="bob:default",
                query="Bob question",
                top_k=3,
                retrieved_json="{}",
                final_answer="Bob answer",
            )
            candidates_path.write_text(
                json.dumps(
                    [
                        {
                            "id": f"feedback_trace_{bob_trace}",
                            "trace_id": bob_trace,
                            "question": "Bob question",
                        },
                        {
                            "id": f"feedback_trace_{alice_trace}",
                            "trace_id": alice_trace,
                            "question": "Alice question",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            identity = AuthIdentity(
                enabled=True,
                authenticated=True,
                user_id="alice",
                requested_session_id="default",
                session_id="alice:default",
                auth_mode="api_token",
            )
            original_store = web.get_sqlite_store
            original_candidates_path = web.EVAL_CANDIDATES_PATH
            try:
                web.get_sqlite_store = lambda: store  # type: ignore[assignment]
                web.EVAL_CANDIDATES_PATH = candidates_path
                candidates = web.load_feedback_eval_candidates(candidates_path)
                visible = [
                    candidate["id"]
                    for candidate in candidates
                    if web.eval_candidate_visible(candidate, identity)
                ]
                assert visible == [f"feedback_trace_{alice_trace}"]
                web.ensure_eval_candidate_access(f"feedback_trace_{alice_trace}", identity)
                try:
                    web.ensure_eval_candidate_access(f"feedback_trace_{bob_trace}", identity)
                except HTTPException as exc:
                    assert exc.status_code == 404
                else:
                    raise AssertionError("Cross-namespace eval candidate should not be visible.")
            finally:
                web.get_sqlite_store = original_store  # type: ignore[assignment]
                web.EVAL_CANDIDATES_PATH = original_candidates_path
        finally:
            store.close()


def main() -> None:
    saved = {name: os.environ.get(name) for name in AUTH_ENV_NAMES}
    try:
        assert_auth_headers()
        assert_session_scoped_storage_filters()
        assert_eval_candidate_namespace_filtering()
    finally:
        clear_auth_env()
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value

    print("Auth smoke test passed.")


if __name__ == "__main__":
    main()
