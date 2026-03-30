from __future__ import annotations

from pathlib import Path

from app.config import load_config
from app.dependencies import  AppDependencies
from app.ollama_client import OllamaChatClient, OllamaEmbeddingClient
from storage.qdrant_store import  QdrantStore
from storage.sqlite_store import SQLiteStore


def bootstrap_app(env_file: str | Path = ".env") -> AppDependencies:
    config = load_config(env_file)

    chat_client = OllamaChatClient(
        base_url=config.ollama_base_url,
        model_name=config.chat_model
    )

    embedding_client = OllamaEmbeddingClient(
        base_url=config.ollama_base_url,
        model_name=config.embed_model
    )

    sqlite_store = SQLiteStore(config.sqlite_path)
    sqlite_store.initialize()

    qdrant_store = QdrantStore(
        storage_path=config.qdrant_path,
        collection_name="knowledge_chunks",
    )

    qdrant_store.connect()

    return AppDependencies(
        config=config,
        chat_client=chat_client,
        embedding_client=embedding_client,
        sqlite_store=sqlite_store,
        qdrant_store=qdrant_store
    )