from __future__ import annotations

from time import perf_counter
from typing import Any, Literal

import requests

from local_agent.app.dependencies import AppDependencies


ComponentStatus = Literal["ok", "warn", "error"]
OverallStatus = Literal["ok", "degraded", "error"]


def build_system_status(
    deps: AppDependencies,
    *,
    check_models: bool = True,
    model_timeout: float = 1.5,
) -> dict[str, Any]:
    started_at = perf_counter()
    components: list[dict[str, Any]] = []

    components.append(_sqlite_status(deps))
    components.append(_qdrant_status(deps))
    components.extend(_ollama_status(deps, check_models=check_models, timeout=model_timeout))
    components.append(_tool_status(deps))

    status = _overall_status(components)
    ok_count = sum(1 for item in components if item["status"] == "ok")
    warn_count = sum(1 for item in components if item["status"] == "warn")
    error_count = sum(1 for item in components if item["status"] == "error")

    return {
        "status": status,
        "components": components,
        "summary": {
            "ok_count": ok_count,
            "warn_count": warn_count,
            "error_count": error_count,
            "document_count": _safe_document_count(deps),
            "tool_count": len(deps.tool_registry.list_tools()),
            "duration_ms": _elapsed_ms(started_at),
        },
    }


def _sqlite_status(deps: AppDependencies) -> dict[str, Any]:
    started_at = perf_counter()
    try:
        ok = deps.sqlite_store.health_check()
    except Exception as exc:
        return _component(
            "SQLite",
            "error",
            f"SQLite check failed: {exc}",
            duration_ms=_elapsed_ms(started_at),
            details={"path": str(deps.config.sqlite_path)},
        )

    return _component(
        "SQLite",
        "ok" if ok else "error",
        "SQLite is reachable." if ok else "SQLite did not return a valid health response.",
        duration_ms=_elapsed_ms(started_at),
        details={
            "path": str(deps.config.sqlite_path),
            "document_count": _safe_document_count(deps),
        },
    )


def _qdrant_status(deps: AppDependencies) -> dict[str, Any]:
    started_at = perf_counter()
    try:
        healthy = deps.qdrant_store.health_check()
        collection_exists = deps.qdrant_store.collection_exists()
    except Exception as exc:
        return _component(
            "Qdrant",
            "error",
            f"Qdrant check failed: {exc}",
            duration_ms=_elapsed_ms(started_at),
            details={
                "path": str(deps.config.qdrant_path),
                "collection": deps.qdrant_store.collection_name,
            },
        )

    if not healthy:
        status: ComponentStatus = "error"
        message = "Qdrant did not return a valid health response."
    elif not collection_exists:
        status = "warn"
        message = "Qdrant is reachable, but the knowledge collection does not exist yet."
    else:
        status = "ok"
        message = "Qdrant is reachable and the knowledge collection exists."

    return _component(
        "Qdrant",
        status,
        message,
        duration_ms=_elapsed_ms(started_at),
        details={
            "path": str(deps.config.qdrant_path),
            "collection": deps.qdrant_store.collection_name,
            "collection_exists": collection_exists,
        },
    )


def _ollama_status(
    deps: AppDependencies,
    *,
    check_models: bool,
    timeout: float,
) -> list[dict[str, Any]]:
    if not check_models:
        return [
            _component(
                "Ollama Chat Model",
                "warn",
                "Model availability check was skipped.",
                details={"model": deps.config.chat_model, "base_url": deps.config.ollama_base_url},
            ),
            _component(
                "Ollama Embedding Model",
                "warn",
                "Model availability check was skipped.",
                details={"model": deps.config.embed_model, "base_url": deps.config.ollama_base_url},
            ),
        ]

    started_at = perf_counter()
    try:
        models = _list_ollama_models(deps.config.ollama_base_url, timeout=timeout)
    except Exception as exc:
        duration_ms = _elapsed_ms(started_at)
        return [
            _component(
                "Ollama Chat Model",
                "error",
                f"Ollama model check failed: {exc}",
                duration_ms=duration_ms,
                details={"model": deps.config.chat_model, "base_url": deps.config.ollama_base_url},
            ),
            _component(
                "Ollama Embedding Model",
                "error",
                f"Ollama model check failed: {exc}",
                duration_ms=duration_ms,
                details={"model": deps.config.embed_model, "base_url": deps.config.ollama_base_url},
            ),
        ]

    duration_ms = _elapsed_ms(started_at)
    return [
        _model_component(
            name="Ollama Chat Model",
            configured_model=deps.config.chat_model,
            models=models,
            base_url=deps.config.ollama_base_url,
            duration_ms=duration_ms,
        ),
        _model_component(
            name="Ollama Embedding Model",
            configured_model=deps.config.embed_model,
            models=models,
            base_url=deps.config.ollama_base_url,
            duration_ms=duration_ms,
        ),
    ]


def _tool_status(deps: AppDependencies) -> dict[str, Any]:
    tools = deps.tool_registry.list_tools()
    approval_count = sum(1 for tool in tools if tool.requires_approval)
    return _component(
        "Tool Registry",
        "ok",
        f"{len(tools)} tools are registered.",
        details={
            "tool_count": len(tools),
            "approval_required_count": approval_count,
            "tools": [tool.name for tool in tools],
        },
    )


def _list_ollama_models(base_url: str, *, timeout: float) -> set[str]:
    response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
    response.raise_for_status()
    data = response.json()
    models = data.get("models") or []
    names: set[str] = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            names.add(name)
        model = item.get("model")
        if isinstance(model, str) and model:
            names.add(model)
    return names


def _model_component(
    *,
    name: str,
    configured_model: str,
    models: set[str],
    base_url: str,
    duration_ms: float,
) -> dict[str, Any]:
    available = configured_model in models
    return _component(
        name,
        "ok" if available else "warn",
        f"{configured_model} is available." if available else f"{configured_model} was not listed by Ollama.",
        duration_ms=duration_ms,
        details={
            "model": configured_model,
            "base_url": base_url,
            "available_model_count": len(models),
        },
    )


def _safe_document_count(deps: AppDependencies) -> int:
    try:
        return deps.sqlite_store.count_documents()
    except Exception:
        return 0


def _overall_status(components: list[dict[str, Any]]) -> OverallStatus:
    if any(component["status"] == "error" for component in components):
        return "error"
    if any(component["status"] == "warn" for component in components):
        return "degraded"
    return "ok"


def _component(
    name: str,
    status: ComponentStatus,
    message: str,
    *,
    duration_ms: float = 0.0,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "message": message,
        "duration_ms": duration_ms,
        "details": details or {},
    }


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)
