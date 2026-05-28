from __future__ import annotations

from pathlib import Path

from agent.memory_manager import MemoryManager
from agent.orchestrator import Orchestrator
from agent.planner import Planner
from agent.schemas import ToolSpec
from agent.verifier import Verifier
from app.config import load_config
from app.dependencies import  AppDependencies
from app.file_mcp import ReadOnlyFileMCPClient
from app.mcp_adapter import MCPToolAdapter
from app.ollama_client import OllamaChatClient, OllamaEmbeddingClient
from app.sqlite_mcp import ReadOnlySQLiteMCPClient
from app.tool_registry import ToolRegistry
from app.weather_tool import CurrentWeatherTool
from retrieval.answer_service import AnswerService
from retrieval.search import RetrievalService
from retrieval.doc_router import DocumentRouter
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
    doc_router = DocumentRouter(sqlite_store=sqlite_store)

    qdrant_store = QdrantStore(
        storage_path=config.qdrant_path,
        collection_name="knowledge_chunks",
    )

    qdrant_store.connect()

    planner = Planner(chat_client=chat_client)
    retrieval_service = RetrievalService(
        qdrant_store=qdrant_store,
        embedding_client=embedding_client,
        sqlite_store=sqlite_store,
        top_k=config.top_k,
        use_reranker=config.use_reranker,
        rerank_model=config.rerank_model,
        rerank_candidates=config.rerank_candidates,
    )
    answer_service = AnswerService(
        chat_client=chat_client
    )
    tool_registry = ToolRegistry()
    tool_registry.register(
        ToolSpec(
            name="list_documents",
            description="List Index documents",
            requires_approval = False,
        ),
        lambda: sqlite_store.list_documents(),
    )
    tool_registry.register(
        ToolSpec(
            name="get_current_weather",
            description="Get current weather for a named location using a read-only web weather API.",
            requires_approval=False,
        ),
        CurrentWeatherTool(),
    )
    if config.file_mcp_enabled:
        file_mcp_client = ReadOnlyFileMCPClient(
            allowed_roots=config.file_mcp_roots,
            base_dir=Path(__file__).resolve().parents[1],
        )
        MCPToolAdapter(
            server_name="local_files",
            client=file_mcp_client,
        ).register_tools(tool_registry)
    MCPToolAdapter(
        server_name="sqlite",
        client=ReadOnlySQLiteMCPClient(sqlite_store),
    ).register_tools(tool_registry)

    memory_manager = MemoryManager(sqlite_store=sqlite_store)
    verifier = Verifier()
    orchestrator = Orchestrator(
        planner=planner,
        retrieval_service=retrieval_service,
        answer_service=answer_service,
        tool_registry=tool_registry,
        memory_manager=memory_manager,
        verifier=verifier,
        sqlite_store=sqlite_store,
        doc_router=doc_router,
        max_steps=3,
    )
   

    return AppDependencies(
        config=config,
        chat_client=chat_client,
        embedding_client=embedding_client,
        sqlite_store=sqlite_store,
        qdrant_store=qdrant_store,
        planner=planner,
        retrieval_service=retrieval_service,
        answer_service=answer_service,
        orchestrator=orchestrator,
        tool_registry=tool_registry,
        memory_manager=memory_manager,
        verifier=verifier,
        
    )
