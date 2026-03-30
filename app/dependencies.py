from __future__ import annotations

from dataclasses import dataclass

from app.config import AppConfig
from app.ollama_client import OllamaChatClient, OllamaEmbeddingClient
from storage.qdrant_store import QdrantStore
from storage.sqlite_store import SQLiteStore

@dataclass(slots=True)
class AppDependencies:
    config: AppConfig
    chat_client: OllamaChatClient
    embedding_client: OllamaEmbeddingClient
    sqlite_store: SQLiteStore
    qdrant_store: QdrantStore