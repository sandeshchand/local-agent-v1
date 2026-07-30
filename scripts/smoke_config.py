from __future__ import annotations

import os
import tempfile
from pathlib import Path

from local_agent.app.config import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_EMBED_MODEL,
    DEFAULT_OLLAMA_BASE_URL,
    load_config,
)
from local_agent.app.paths import DEFAULT_QDRANT_PATH, DEFAULT_SQLITE_PATH


CONFIG_ENV_NAMES = [
    "OLLAMA_BASE_URL",
    "CHAT_MODEL",
    "EMBED_MODEL",
    "QDRANT_PATH",
    "SQLITE_PATH",
    "TOP_K",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "DEBUG",
    "USE_RERANKER",
    "RERANKER_MODEL",
    "RERANK_CANDIDATES",
    "WARM_RETRIEVAL_ON_STARTUP",
    "EMBEDDING_CACHE_SIZE",
    "DOCUMENT_ROUTER_CACHE_ENABLED",
    "FILE_MCP_ENABLED",
    "FILE_MCP_ROOTS",
    "AUTH_ENABLED",
    "AUTH_TOKEN",
]


def clear_config_env() -> None:
    for name in CONFIG_ENV_NAMES:
        os.environ.pop(name, None)


def restore_config_env(saved: dict[str, str | None]) -> None:
    clear_config_env()
    for name, value in saved.items():
        if value is not None:
            os.environ[name] = value


def assert_missing_env_uses_safe_defaults() -> None:
    clear_config_env()
    os.environ["DEBUG"] = "release"

    config = load_config("__missing_local_agent.env")

    assert config.ollama_base_url == DEFAULT_OLLAMA_BASE_URL
    assert config.chat_model == DEFAULT_CHAT_MODEL
    assert config.embed_model == DEFAULT_EMBED_MODEL
    assert config.qdrant_path == DEFAULT_QDRANT_PATH.resolve()
    assert config.sqlite_path == DEFAULT_SQLITE_PATH.resolve()
    assert config.debug is False
    assert config.embedding_cache_size == 128
    assert config.document_router_cache_enabled is True
    assert config.auth_enabled is False
    assert config.auth_token == ""


def assert_env_file_relative_paths_are_stable() -> None:
    clear_config_env()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        env_file = tmp_path / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "OLLAMA_BASE_URL=http://localhost:11434",
                    "CHAT_MODEL=test-chat",
                    "EMBED_MODEL=test-embed",
                    "QDRANT_PATH=./qdrant",
                    "SQLITE_PATH=./sqlite/app.db",
                    "DEBUG=yes",
                    "EMBEDDING_CACHE_SIZE=7",
                    "DOCUMENT_ROUTER_CACHE_ENABLED=no",
                    "FILE_MCP_ROOTS=docs,README.md",
                    "AUTH_ENABLED=yes",
                    "AUTH_TOKEN=local-dev-token",
                ]
            ),
            encoding="utf-8",
        )

        config = load_config(env_file)

        assert config.qdrant_path == (tmp_path / "qdrant").resolve()
        assert config.sqlite_path == (tmp_path / "sqlite" / "app.db").resolve()
        assert config.debug is True
        assert config.embedding_cache_size == 7
        assert config.document_router_cache_enabled is False
        assert config.file_mcp_roots == [
            (tmp_path / "docs").resolve(),
            (tmp_path / "README.md").resolve(),
        ]
        assert config.auth_enabled is True
        assert config.auth_token == "local-dev-token"


def assert_auth_enabled_requires_token() -> None:
    clear_config_env()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        env_file = tmp_path / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "OLLAMA_BASE_URL=http://localhost:11434",
                    "CHAT_MODEL=test-chat",
                    "EMBED_MODEL=test-embed",
                    "QDRANT_PATH=./qdrant",
                    "SQLITE_PATH=./sqlite/app.db",
                    "AUTH_ENABLED=true",
                ]
            ),
            encoding="utf-8",
        )
        try:
            load_config(env_file)
        except ValueError as exc:
            assert "AUTH_TOKEN" in str(exc)
        else:
            raise AssertionError("AUTH_ENABLED=true should require AUTH_TOKEN.")


def main() -> None:
    saved = {name: os.environ.get(name) for name in CONFIG_ENV_NAMES}
    try:
        assert_missing_env_uses_safe_defaults()
        assert_env_file_relative_paths_are_stable()
        assert_auth_enabled_requires_token()
    finally:
        restore_config_env(saved)

    print("Config smoke test passed.")


if __name__ == "__main__":
    main()
