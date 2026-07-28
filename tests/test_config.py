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
]


def _clear_config_env(monkeypatch) -> None:
    for name in CONFIG_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_load_config_uses_safe_defaults_when_env_file_is_missing(monkeypatch) -> None:
    _clear_config_env(monkeypatch)
    monkeypatch.setenv("DEBUG", "release")

    config = load_config("__missing_local_agent.env")

    assert config.ollama_base_url == DEFAULT_OLLAMA_BASE_URL
    assert config.chat_model == DEFAULT_CHAT_MODEL
    assert config.embed_model == DEFAULT_EMBED_MODEL
    assert config.qdrant_path == DEFAULT_QDRANT_PATH.resolve()
    assert config.sqlite_path == DEFAULT_SQLITE_PATH.resolve()
    assert config.debug is False
    assert config.warm_retrieval_on_startup is False
    assert config.embedding_cache_size == 128
    assert config.document_router_cache_enabled is True


def test_load_config_resolves_relative_paths_from_env_file(tmp_path, monkeypatch) -> None:
    _clear_config_env(monkeypatch)
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
                "WARM_RETRIEVAL_ON_STARTUP=yes",
                "EMBEDDING_CACHE_SIZE=7",
                "DOCUMENT_ROUTER_CACHE_ENABLED=no",
                "FILE_MCP_ROOTS=docs,README.md",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(env_file)

    assert config.qdrant_path == (tmp_path / "qdrant").resolve()
    assert config.sqlite_path == (tmp_path / "sqlite" / "app.db").resolve()
    assert config.debug is True
    assert config.warm_retrieval_on_startup is True
    assert config.embedding_cache_size == 7
    assert config.document_router_cache_enabled is False
    assert config.file_mcp_roots == [
        (tmp_path / "docs").resolve(),
        (tmp_path / "README.md").resolve(),
    ]
