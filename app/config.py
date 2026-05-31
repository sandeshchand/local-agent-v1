from __future__ import annotations

from pathlib import Path
import os

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


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
    load_dotenv(dotenv_path=env_file, override=True)
    base_dir = Path(env_file).resolve().parent

    data = {
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "CHAT_MODEL": os.getenv("CHAT_MODEL"),
        "EMBED_MODEL": os.getenv("EMBED_MODEL"),
        "QDRANT_PATH": os.getenv("QDRANT_PATH"),
        "SQLITE_PATH": os.getenv("SQLITE_PATH"),
        "TOP_K": os.getenv("TOP_K", "5"),
        "CHUNK_SIZE": os.getenv("CHUNK_SIZE", "900"),
        "CHUNK_OVERLAP": os.getenv("CHUNK_OVERLAP", "120"),
        "DEBUG": os.getenv("DEBUG", "false"),
        "USE_RERANKER": os.getenv("USE_RERANKER", "true"),
        "RERANKER_MODEL": os.getenv
            ("RERANKER_MODEL", 
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
            ),
        "RERANK_CANDIDATES": os.getenv("RERANK_CANDIDATES", "8"),
        "FILE_MCP_ENABLED": os.getenv("FILE_MCP_ENABLED", "true"),
        "FILE_MCP_ROOTS": _parse_path_list(
            os.getenv("FILE_MCP_ROOTS", "data,docs,benchmarks,tests,README.md,pyproject.toml"),
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
