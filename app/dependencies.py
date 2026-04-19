from __future__ import annotations

from dataclasses import dataclass

from agent.memory_manager import MemoryManager
from agent.orchestrator import Orchestrator
from agent.planner import Planner
from agent.verifier import Verifier
from app.config import AppConfig
from app.ollama_client import OllamaChatClient, OllamaEmbeddingClient
from app.tool_registry import ToolRegistry
from retrieval.answer_service import AnswerService
from retrieval.search import RetrievalService
from storage.qdrant_store import QdrantStore
from storage.sqlite_store import SQLiteStore

@dataclass(slots=True)
class AppDependencies:
    config: AppConfig
    chat_client: OllamaChatClient
    embedding_client: OllamaEmbeddingClient
    sqlite_store: SQLiteStore
    qdrant_store: QdrantStore
    planner: Planner
    retrieval_service: RetrievalService
    answer_service: AnswerService
    orchestrator: Orchestrator
    tool_registry: ToolRegistry
    memory_manager: MemoryManager
    verifier: Verifier