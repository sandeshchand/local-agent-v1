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


def load_config(env_file: str | Path = ".env") -> AppConfig:
    load_dotenv(dotenv_path=env_file)

    data = {
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL"),
        "CHAT_MODEL": os.getenv("CHAT_MODEL"),
        "EMBED_MODEL": os.getenv("EMBED_MODEL"),
        "QDRANT_PATH": os.getenv("QDRANT_PATH"),
        "SQLITE_PATH": os.getenv("SQLITE_PATH"),
        "TOP_K": os.getenv("TOP_K", "5"),
        "CHUNK_SIZE": os.getenv("CHUNK_SIZE", "800"),
        "CHUNK_OVERLAP": os.getenv("CHUNK_OVERLAP", "120"),
        "DEBUG": os.getenv("DEBUG", "false"),
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
    )