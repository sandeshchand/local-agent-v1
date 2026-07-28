from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

from local_agent.app.config import load_config
from local_agent.llm import OllamaEmbeddingClient
from local_agent.retrieval.doc_router import DocumentRouter
from local_agent.retrieval.search import RetrievalService
from local_agent.storage.qdrant_store import QdrantStore
from local_agent.storage.sqlite_store import SQLiteStore


ROOT = Path(__file__).resolve().parents[1]


SCALE_PROFILES: dict[str, list[str]] = {
    "multi-doc-representative": [
        "sora_prompt_following",
        "docker_lazydocker_features",
        "docker_watchtower_features",
        "ml_tsetlin_machine",
        "ml_crfs",
        "python_builtin_http_server",
        "python_large_numbers",
        "ai_coding_multi_agent_architecture",
        "pydantic_env_file_purpose",
        "smoldocling_app_pipeline",
        "intro_three_part_formula",
        "ai_money_starting_steps",
    ],
}


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)

    position = (len(ordered) - 1) * (percentile_value / 100)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    value = ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction
    return round(value, 2)


def timed(action: Callable[[], Any]) -> tuple[float, Any]:
    started_at = time.perf_counter()
    value = action()
    return round((time.perf_counter() - started_at) * 1000, 2), value


def load_eval_items(eval_path: Path, ids: str, limit: int | None) -> list[dict[str, Any]]:
    items = json.loads(eval_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError(f"Expected {eval_path} to contain a JSON list")

    selected_ids = {item.strip() for item in ids.split(",") if item.strip()}
    if selected_ids:
        items = [item for item in items if str(item.get("id", "")) in selected_ids]
        missing_ids = selected_ids - {str(item.get("id", "")) for item in items}
        if missing_ids:
            missing = ", ".join(sorted(missing_ids))
            raise ValueError(f"Eval ids not found: {missing}")

    if limit is not None and not selected_ids:
        items = items[: max(0, int(limit))]
    return items


def corpus_summary(sqlite_store: SQLiteStore) -> dict[str, Any]:
    signature = sqlite_store.routing_corpus_signature()
    latest_documents = sqlite_store.list_documents(limit=5)
    return {
        "signature_version": signature[0],
        "document_count": signature[1],
        "chunk_count": signature[2],
        "chunk_text_size": signature[3],
        "token_estimate_total": signature[4],
        "latest_indexed_at": signature[5],
        "max_checksum": signature[6],
        "latest_documents": [
            {
                "doc_id": item.get("doc_id", ""),
                "title": item.get("title", ""),
                "source_path": item.get("source_path", ""),
                "page_count": item.get("page_count", 0),
                "indexed_at": item.get("indexed_at", ""),
            }
            for item in latest_documents
        ],
    }


def summarize_top_docs(routed_docs: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": item.get("doc_id", ""),
            "title": item.get("title", ""),
            "score": round(float(item.get("routing_score", 0.0)), 4),
        }
        for item in routed_docs[:limit]
    ]


def profile_routing(
    sqlite_store: SQLiteStore,
    queries: list[dict[str, Any]],
    top_n: int,
) -> dict[str, Any]:
    router = DocumentRouter(sqlite_store=sqlite_store, cache_enabled=True)
    items: list[dict[str, Any]] = []

    for query_item in queries:
        question = str(query_item.get("question", ""))
        router.clear_cache()
        cold_ms, cold_docs = timed(lambda: router.route(question, top_n=top_n))
        warm_ms, warm_docs = timed(lambda: router.route(question, top_n=top_n))
        items.append(
            {
                "id": query_item.get("id", ""),
                "question": question,
                "cold_ms": cold_ms,
                "warm_ms": warm_ms,
                "top_docs": summarize_top_docs([dict(item) for item in warm_docs], top_n),
                "cold_top_docs": summarize_top_docs([dict(item) for item in cold_docs], top_n),
            }
        )

    cold_values = [float(item["cold_ms"]) for item in items]
    warm_values = [float(item["warm_ms"]) for item in items]
    average_cold = round(statistics.mean(cold_values), 2) if cold_values else 0.0
    average_warm = round(statistics.mean(warm_values), 2) if warm_values else 0.0
    return {
        "ok": True,
        "top_n": top_n,
        "average_cold_ms": average_cold,
        "average_warm_ms": average_warm,
        "p95_cold_ms": percentile(cold_values, 95),
        "p95_warm_ms": percentile(warm_values, 95),
        "warmup_savings_ms": round(average_cold - average_warm, 2),
        "items": items,
    }


def profile_embedding_cache(config: Any, queries: list[dict[str, Any]]) -> dict[str, Any]:
    embedding_client = OllamaEmbeddingClient(
        base_url=config.ollama_base_url,
        model_name=config.embed_model,
        cache_size=config.embedding_cache_size,
    )
    items: list[dict[str, Any]] = []

    try:
        for query_item in queries:
            question = str(query_item.get("question", ""))
            probe_text = f"{question}\n[retrieval-scale-profile:{query_item.get('id', '')}]"
            cold_ms, vector = timed(lambda: embedding_client.embed(probe_text))
            warm_ms, warm_vector = timed(lambda: embedding_client.embed(probe_text))
            items.append(
                {
                    "id": query_item.get("id", ""),
                    "question": question,
                    "cold_ms": cold_ms,
                    "warm_ms": warm_ms,
                    "vector_size": len(vector),
                    "warm_vector_size": len(warm_vector),
                }
            )
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "items": items,
        }

    cold_values = [float(item["cold_ms"]) for item in items]
    warm_values = [float(item["warm_ms"]) for item in items]
    average_cold = round(statistics.mean(cold_values), 2) if cold_values else 0.0
    average_warm = round(statistics.mean(warm_values), 2) if warm_values else 0.0
    return {
        "ok": True,
        "model": config.embed_model,
        "cache_size": config.embedding_cache_size,
        "average_cold_ms": average_cold,
        "average_warm_ms": average_warm,
        "p95_cold_ms": percentile(cold_values, 95),
        "p95_warm_ms": percentile(warm_values, 95),
        "warmup_savings_ms": round(average_cold - average_warm, 2),
        "items": items,
    }


def summarize_search_results(results: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": item.get("doc_id", ""),
            "chunk_id": item.get("chunk_id", ""),
            "title": item.get("title", ""),
            "page_number": item.get("page_number", ""),
            "source": item.get("source", ""),
            "score": round(float(item.get("score", 0.0)), 4),
        }
        for item in results[:limit]
    ]


def profile_retrieval_search(
    config: Any,
    sqlite_store: SQLiteStore,
    queries: list[dict[str, Any]],
    repeat: int,
    warmup: bool,
) -> dict[str, Any]:
    qdrant_store = QdrantStore(
        storage_path=config.qdrant_path,
        collection_name="knowledge_chunks",
    )
    embedding_client = OllamaEmbeddingClient(
        base_url=config.ollama_base_url,
        model_name=config.embed_model,
        cache_size=config.embedding_cache_size,
    )
    retrieval_service = RetrievalService(
        qdrant_store=qdrant_store,
        sqlite_store=sqlite_store,
        embedding_client=embedding_client,
        top_k=config.top_k,
        use_reranker=config.use_reranker,
        rerank_model=config.rerank_model,
        rerank_candidates=config.rerank_candidates,
    )
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    warmup_report = retrieval_service.warm_up() if warmup else None

    try:
        for run_index in range(1, max(1, repeat) + 1):
            for query_item in queries:
                question = str(query_item.get("question", ""))
                try:
                    elapsed_ms, results = timed(lambda: retrieval_service.search(question))
                except Exception as exc:
                    errors.append(
                        {
                            "id": str(query_item.get("id", "")),
                            "run": str(run_index),
                            "error": str(exc),
                        }
                    )
                    continue
                items.append(
                    {
                        "run": run_index,
                        "id": query_item.get("id", ""),
                        "question": question,
                        "total_ms": elapsed_ms,
                        "result_count": len(results),
                        "top_results": summarize_search_results(results),
                    }
                )
    finally:
        qdrant_store.close()

    latencies = [float(item["total_ms"]) for item in items]
    return {
        "ok": not errors,
        "repeat": max(1, repeat),
        "query_count": len(queries),
        "measurement_count": len(items),
        "average_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "max_ms": round(max(latencies), 2) if latencies else 0.0,
        "slowest": max(items, key=lambda item: item["total_ms"]) if items else None,
        "warmup": warmup_report,
        "items": items,
        "errors": errors,
    }


def qdrant_summary(config: Any) -> dict[str, Any]:
    return {
        "mode": "local_path",
        "storage_path": str(config.qdrant_path),
        "collection_name": "knowledge_chunks",
        "note": (
            "Local path mode is intended for one local process. "
            "Use server mode before multiple web workers or concurrent app processes."
        ),
    }


def build_recommendations(report: dict[str, Any]) -> list[str]:
    corpus = report.get("corpus") or {}
    routing = report.get("routing") or {}
    embedding = report.get("embedding_cache") or {}
    retrieval = report.get("retrieval_search") or {}
    qdrant = report.get("qdrant") or {}

    doc_count = int(corpus.get("document_count") or 0)
    chunk_count = int(corpus.get("chunk_count") or 0)
    recommendations: list[str] = []

    if doc_count >= 1000 or chunk_count >= 50000:
        recommendations.append(
            "High priority: move Qdrant to server mode before scaling further."
        )
    elif doc_count >= 100 or chunk_count >= 10000:
        recommendations.append(
            "Medium priority: start Qdrant server-mode testing with this corpus size."
        )
    else:
        recommendations.append(
            "Current corpus size is still suitable for local path mode during development."
        )

    if qdrant.get("mode") == "local_path":
        recommendations.append(
            "Keep only one local app process open when using Qdrant path mode."
        )

    if routing.get("ok"):
        cold = float(routing.get("average_cold_ms") or 0.0)
        warm = float(routing.get("average_warm_ms") or 0.0)
        if cold > 0 and warm <= cold * 0.5:
            recommendations.append("Document-router cache is effective; keep it enabled.")
        elif cold > 250:
            recommendations.append(
                "Routing cold-build time is noticeable; inspect routing corpus size and cache invalidation."
            )

    if embedding.get("ok"):
        cold = float(embedding.get("average_cold_ms") or 0.0)
        warm = float(embedding.get("average_warm_ms") or 0.0)
        if cold > 0 and warm <= cold * 0.2:
            recommendations.append("Repeated-query embedding cache is effective.")
    elif embedding.get("error"):
        recommendations.append(
            "Embedding profiling failed; check that Ollama is running and the embedding model is available."
        )

    if retrieval.get("errors"):
        recommendations.append(
            "Retrieval search profiling had errors; if Qdrant is locked, stop duplicate web/CLI processes."
        )
    elif retrieval.get("measurement_count"):
        p95 = float(retrieval.get("p95_ms") or 0.0)
        if p95 > 1000:
            recommendations.append(
                "Retrieval search p95 is high; inspect reranker cost, Qdrant mode, and candidate limits."
            )
        else:
            recommendations.append("Retrieval search p95 is healthy for the sampled queries.")

    return recommendations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile retrieval scaling signals.")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Environment file used for SQLite, Qdrant, and Ollama settings.",
    )
    parser.add_argument(
        "--eval-file",
        default="benchmarks/gold_qa/eval_multi_doc_rag.json",
        help="Gold QA JSON file used for representative queries.",
    )
    parser.add_argument(
        "--output",
        default="var/logs/retrieval_scale_profile.json",
        help="JSON report output path.",
    )
    parser.add_argument(
        "--ids",
        default="",
        help="Comma-separated eval IDs to profile.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(SCALE_PROFILES.keys()),
        default="",
        help="Named representative eval profile.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=6,
        help="Number of eval questions when --ids or --profile is not provided.",
    )
    parser.add_argument(
        "--top-docs",
        type=int,
        default=3,
        help="Number of routed document candidates to collect.",
    )
    parser.add_argument(
        "--repeat-search",
        type=int,
        default=2,
        help="Number of retrieval-search repeats for cache/stability visibility.",
    )
    parser.add_argument(
        "--skip-embedding",
        action="store_true",
        help="Skip live Ollama embedding cache timing.",
    )
    parser.add_argument(
        "--skip-search",
        action="store_true",
        help="Skip live Qdrant retrieval-search timing.",
    )
    parser.add_argument(
        "--warmup-retrieval",
        action="store_true",
        help="Warm Qdrant, embeddings, and reranker before measuring retrieval search.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.ids and args.profile:
        print("ERROR: Use either --ids or --profile, not both.")
        sys.exit(1)

    ids = args.ids
    if args.profile:
        ids = ",".join(SCALE_PROFILES[args.profile])

    try:
        config = load_config(ROOT / args.env_file)
        queries = load_eval_items(ROOT / args.eval_file, ids, args.limit)
        if not queries:
            raise ValueError("No eval queries selected for retrieval scale profiling")

        sqlite_store = SQLiteStore(config.sqlite_path)
        sqlite_store.initialize()
        report: dict[str, Any] = {
            "env_file": str(ROOT / args.env_file),
            "eval_file": str(ROOT / args.eval_file),
            "profile": args.profile,
            "selected_query_count": len(queries),
            "selected_query_ids": [item.get("id", "") for item in queries],
            "corpus": corpus_summary(sqlite_store),
            "qdrant": qdrant_summary(config),
            "routing": profile_routing(sqlite_store, queries, top_n=args.top_docs),
        }
        if args.skip_embedding:
            report["embedding_cache"] = {"ok": None, "skipped": True}
        else:
            report["embedding_cache"] = profile_embedding_cache(config, queries)

        if args.skip_search:
            report["retrieval_search"] = {"ok": None, "skipped": True}
        else:
            report["retrieval_search"] = profile_retrieval_search(
                config=config,
                sqlite_store=sqlite_store,
                queries=queries,
                repeat=args.repeat_search,
                warmup=args.warmup_retrieval,
            )

        report["recommendations"] = build_recommendations(report)
        sqlite_store.close()
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    corpus = report["corpus"]
    routing = report["routing"]
    retrieval = report.get("retrieval_search") or {}
    print("Retrieval scale profile complete")
    print(f"Documents: {corpus['document_count']}")
    print(f"Chunks: {corpus['chunk_count']}")
    print(
        "Routing avg cold/warm: "
        f"{routing['average_cold_ms']} ms / {routing['average_warm_ms']} ms"
    )
    if retrieval.get("measurement_count"):
        print(f"Retrieval search p95: {retrieval['p95_ms']} ms")
    elif retrieval.get("errors"):
        print(f"Retrieval search errors: {len(retrieval['errors'])}")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
