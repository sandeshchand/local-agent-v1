from __future__ import annotations

from dataclasses import dataclass

from local_agent.agent.memory_manager import MemoryManager
from local_agent.agent.orchestrator import Orchestrator
from local_agent.agent.planner import Planner
from local_agent.agent.verifier import Verifier
from local_agent.app.config import AppConfig
from local_agent.app.ollama_client import OllamaChatClient, OllamaEmbeddingClient
from local_agent.app.tool_registry import ToolRegistry
from local_agent.retrieval.answer_service import AnswerService
from local_agent.retrieval.search import RetrievalService
from local_agent.storage.qdrant_store import QdrantStore
from local_agent.storage.sqlite_store import SQLiteStore

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