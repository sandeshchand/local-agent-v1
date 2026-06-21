from __future__ import annotations

from pathlib import Path
import os

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from local_agent.app.paths import DEFAULT_QDRANT_PATH, DEFAULT_SQLITE_PATH, PROJECT_ROOT


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_CHAT_MODEL = "qwen2.5:7b-instruct"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_FILE_MCP_ROOTS = "data,docs,benchmarks,tests,README.md,pyproject.toml"


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    ollama_base_url: str = Field(..., alias="OLLAMA_BASE_URL")
    chat_model: str = Field(..., alias="CHAT_MODEL")
    embed_model: str = Field(..., alias="EMBED_MODEL")
    qdrant_path: Path = Field(..., alias="QDRANT_PATH")
    sqlite_path: Path = Field(..., alias="SQLITE_PATH")
    top_k: int = Field(5, alias="TOP_K")
    chunk_size: int = Field(800, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(120, alias="CHUNK_OVERLAP")
    debug: bool = Field(False, alias="DEBUG")
    use_reranker: bool = Field(True, alias="USE_RERANKER")
    rerank_model: str = Field(
        "cross-encoder/ms-marco-MiniLM-L-6-v2",
         alias="RERANKER_MODEL",
        )
    rerank_candidates: int = Field(8, alias="RERANK_CANDIDATES")
    file_mcp_enabled: bool = Field(True, alias="FILE_MCP_ENABLED")
    file_mcp_roots: list[Path] = Field(default_factory=list, alias="FILE_MCP_ROOTS")


def load_config(env_file: str | Path = ".env") -> AppConfig:
    env_path = Path(env_file).expanduser()
    if not env_path.is_absolute():
        env_path = PROJECT_ROOT / env_path
    env_path = env_path.resolve()

    load_dotenv(dotenv_path=env_path, override=True)
    base_dir = env_path.parent

    data = {
        "OLLAMA_BASE_URL": _env("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
        "CHAT_MODEL": _env("CHAT_MODEL", DEFAULT_CHAT_MODEL),
        "EMBED_MODEL": _env("EMBED_MODEL", DEFAULT_EMBED_MODEL),
        "QDRANT_PATH": _resolve_path(_env("QDRANT_PATH"), base_dir, DEFAULT_QDRANT_PATH),
        "SQLITE_PATH": _resolve_path(_env("SQLITE_PATH"), base_dir, DEFAULT_SQLITE_PATH),
        "TOP_K": os.getenv("TOP_K", "5"),
        "CHUNK_SIZE": os.getenv("CHUNK_SIZE", "900"),
        "CHUNK_OVERLAP": os.getenv("CHUNK_OVERLAP", "120"),
        "DEBUG": _parse_bool_env("DEBUG", False),
        "USE_RERANKER": _parse_bool_env("USE_RERANKER", True),
        "RERANKER_MODEL": _env("RERANKER_MODEL", DEFAULT_RERANKER_MODEL),
        "RERANK_CANDIDATES": os.getenv("RERANK_CANDIDATES", "8"),
        "FILE_MCP_ENABLED": _parse_bool_env("FILE_MCP_ENABLED", True),
        "FILE_MCP_ROOTS": _parse_path_list(
            _env("FILE_MCP_ROOTS", DEFAULT_FILE_MCP_ROOTS),
            base_dir=base_dir,
        ),
    }

    config = AppConfig.model_validate(data)

    qdrant_path = config.qdrant_path.expanduser().resolve()
    sqlite_path = config.sqlite_path.expanduser().resolve()

    qdrant_path.mkdir(parents=True, exist_ok=True)

    if sqlite_path.parent != sqlite_path:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        OLLAMA_BASE_URL=config.ollama_base_url,
        CHAT_MODEL=config.chat_model,
        EMBED_MODEL=config.embed_model,
        QDRANT_PATH=qdrant_path,
        SQLITE_PATH=sqlite_path,
        TOP_K=config.top_k,
        CHUNK_SIZE=config.chunk_size,
        CHUNK_OVERLAP=config.chunk_overlap,
        DEBUG=config.debug,
        USE_RERANKER=config.use_reranker,
        RERANKER_MODEL=config.rerank_model,
        RERANK_CANDIDATES=config.rerank_candidates,
        FILE_MCP_ENABLED=config.file_mcp_enabled,
        FILE_MCP_ROOTS=config.file_mcp_roots,
    )


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _resolve_path(raw: str | None, base_dir: Path, default: Path) -> Path:
    if raw is None:
        return default

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _parse_path_list(raw: str, base_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for part in raw.split(","):
        value = part.strip()
        if not value:
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = base_dir / path
        paths.append(path.resolve())
    return paths
