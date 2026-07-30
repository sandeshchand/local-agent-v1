from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

COMPILE_TARGETS = [
    "src/local_agent/agent/orchestrator.py",
    "src/local_agent/agent/planner.py",
    "src/local_agent/agent/guardrails.py",
    "src/local_agent/agent/schemas.py",
    "src/local_agent/app/bootstrap.py",
    "src/local_agent/app/auth.py",
    "src/local_agent/app/cli.py",
    "src/local_agent/app/main.py",
    "src/local_agent/app/system_status.py",
    "src/local_agent/app/tool_audit.py",
    "src/local_agent/app/web.py",
    "src/local_agent/app/api_models.py",
    "src/local_agent/llm/ollama_client.py",
    "src/local_agent/operations/__init__.py",
    "src/local_agent/operations/runtime_backup.py",
    "src/local_agent/ingestion/chunking.py",
    "src/local_agent/ingestion/file_loader.py",
    "src/local_agent/ingestion/metadata.py",
    "src/local_agent/ingestion/pipeline.py",
    "src/local_agent/ingestion/parsers/pdf_parser.py",
    "src/local_agent/tools/tool_registry.py",
    "src/local_agent/tools/weather_tool.py",
    "src/local_agent/tools/file_mcp.py",
    "src/local_agent/tools/sqlite_mcp.py",
    "src/local_agent/tools/mcp_adapter.py",
    "src/local_agent/evaluation/eval_candidates.py",
    "src/local_agent/evaluation/memory_eval.py",
    "src/local_agent/evaluation/eval_runner.py",
    "src/local_agent/answering/service.py",
    "src/local_agent/answering/prompts.py",
    "src/local_agent/answering/tool_outputs.py",
    "src/local_agent/answering/source_windows.py",
    "src/local_agent/answering/evidence_facts.py",
    "src/local_agent/answering/extractors.py",
    "src/local_agent/answering/extractive/best_practices.py",
    "src/local_agent/answering/extractive/capabilities.py",
    "src/local_agent/answering/extractive/definitions.py",
    "src/local_agent/answering/extractive/explanations.py",
    "src/local_agent/answering/extractive/limitations.py",
    "src/local_agent/answering/extractive/lists.py",
    "src/local_agent/answering/extractive/processes.py",
    "src/local_agent/answering/extractive/utilities.py",
    "src/local_agent/answering/query_intent.py",
    "src/local_agent/answering/cleaning.py",
    "src/local_agent/retrieval/context_expansion.py",
    "src/local_agent/retrieval/query_terms.py",
    "src/local_agent/retrieval/search.py",
    "src/local_agent/storage/sqlite_store.py",
    "scripts/smoke_memory.py",
    "scripts/smoke_memory_api.py",
    "scripts/eval_memory_quality.py",
    "scripts/smoke_memory_eval.py",
    "scripts/runtime_state.py",
    "scripts/smoke_answer_cleaning.py",
    "scripts/smoke_answer_fact_coverage.py",
    "scripts/smoke_focused_list_extractor.py",
    "scripts/smoke_answer_sequence_extractors.py",
    "scripts/smoke_answer_generation_budget.py",
    "scripts/smoke_evidence_prefilter.py",
    "scripts/smoke_performance_caches.py",
    "scripts/smoke_config.py",
    "scripts/smoke_auth.py",
    "scripts/smoke_empty_index.py",
    "scripts/smoke_ingestion_status.py",
    "scripts/smoke_ingestion_status_api.py",
    "scripts/smoke_qdrant_doc_cleanup.py",
    "scripts/smoke_sqlite_threading.py",
    "scripts/smoke_system_status.py",
    "scripts/smoke_runtime_backup.py",
    "scripts/smoke_document_library.py",
    "scripts/smoke_feedback_analytics.py",
    "scripts/smoke_eval_candidates.py",
    "scripts/smoke_eval_candidate_review.py",
    "scripts/smoke_eval_candidate_run.py",
    "scripts/audit_gold_qa_coverage.py",
    "scripts/smoke_gold_qa_coverage.py",
    "scripts/smoke_feedback_issue_tags.py",
    "scripts/smoke_guardrails.py",
    "scripts/smoke_tool_audit.py",
    "scripts/smoke_file_mcp.py",
    "scripts/smoke_mcp_adapter.py",
    "scripts/smoke_sqlite_mcp.py",
    "scripts/smoke_tool_approval_ui.py",
    "scripts/smoke_weather_tool.py",
    "scripts/query_visual_world.py",
    "scripts/benchmark_latency.py",
    "scripts/profile_retrieval_scale.py",
    "scripts/eval_rag_quality.py",
    "tests/test_config.py",
    "tests/test_paths.py",
]

DEFAULT_FOCUSED_IDS = ",".join(
    [
        "docker_lazydocker_features",
        "docker_watchtower_features",
        "ml_crfs",
        "sora_world_simulator",
    ]
)


def run_step(name: str, command: list[str]) -> None:
    print(f"\n== {name} ==", flush=True)
    print(" ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local regression checks.")
    parser.add_argument(
        "--skip-rag",
        action="store_true",
        help="Run only compile and smoke checks.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run the full RAG benchmark instead of the focused subset.",
    )
    parser.add_argument(
        "--ids",
        default=DEFAULT_FOCUSED_IDS,
        help="Comma-separated eval IDs for focused RAG regression.",
    )
    parser.add_argument(
        "--output",
        default="var/logs/rag_quality_regression_report.json",
        help="Output path for the RAG eval report.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    run_step(
        "Python compile",
        [
            sys.executable,
            "-m",
            "py_compile",
            *COMPILE_TARGETS,
        ],
    )
    run_step("Answer cleaning smoke", [sys.executable, "scripts/smoke_answer_cleaning.py"])
    run_step("Answer fact coverage smoke", [sys.executable, "scripts/smoke_answer_fact_coverage.py"])
    run_step("Focused list extractor smoke", [sys.executable, "scripts/smoke_focused_list_extractor.py"])
    run_step("Answer sequence extractor smoke", [sys.executable, "scripts/smoke_answer_sequence_extractors.py"])
    run_step("Answer generation budget smoke", [sys.executable, "scripts/smoke_answer_generation_budget.py"])
    run_step("Evidence prefilter smoke", [sys.executable, "scripts/smoke_evidence_prefilter.py"])
    run_step("Performance cache smoke", [sys.executable, "scripts/smoke_performance_caches.py"])
    run_step("Config smoke", [sys.executable, "scripts/smoke_config.py"])
    run_step("Auth smoke", [sys.executable, "scripts/smoke_auth.py"])
    run_step("Empty index smoke", [sys.executable, "scripts/smoke_empty_index.py"])
    run_step("Ingestion status smoke", [sys.executable, "scripts/smoke_ingestion_status.py"])
    run_step("Ingestion status API smoke", [sys.executable, "scripts/smoke_ingestion_status_api.py"])
    run_step("Qdrant document cleanup smoke", [sys.executable, "scripts/smoke_qdrant_doc_cleanup.py"])
    run_step("Memory smoke", [sys.executable, "scripts/smoke_memory.py"])
    run_step("Memory API smoke", [sys.executable, "scripts/smoke_memory_api.py"])
    run_step("Memory eval smoke", [sys.executable, "scripts/smoke_memory_eval.py"])
    run_step("Runtime backup smoke", [sys.executable, "scripts/smoke_runtime_backup.py"])
    run_step("SQLite threading smoke", [sys.executable, "scripts/smoke_sqlite_threading.py"])
    run_step("System status smoke", [sys.executable, "scripts/smoke_system_status.py"])
    run_step("Document library smoke", [sys.executable, "scripts/smoke_document_library.py"])
    run_step("Feedback analytics smoke", [sys.executable, "scripts/smoke_feedback_analytics.py"])
    run_step("Feedback eval candidate smoke", [sys.executable, "scripts/smoke_eval_candidates.py"])
    run_step("Eval candidate review smoke", [sys.executable, "scripts/smoke_eval_candidate_review.py"])
    run_step("Eval candidate run smoke", [sys.executable, "scripts/smoke_eval_candidate_run.py"])
    run_step("Gold QA coverage smoke", [sys.executable, "scripts/smoke_gold_qa_coverage.py"])
    run_step("Feedback issue tag smoke", [sys.executable, "scripts/smoke_feedback_issue_tags.py"])
    run_step("Guardrails smoke", [sys.executable, "scripts/smoke_guardrails.py"])
    run_step("Tool audit smoke", [sys.executable, "scripts/smoke_tool_audit.py"])
    run_step("File MCP smoke", [sys.executable, "scripts/smoke_file_mcp.py"])
    run_step("MCP adapter smoke", [sys.executable, "scripts/smoke_mcp_adapter.py"])
    run_step("SQLite MCP smoke", [sys.executable, "scripts/smoke_sqlite_mcp.py"])
    run_step("Tool approval UI smoke", [sys.executable, "scripts/smoke_tool_approval_ui.py"])
    run_step("Weather tool smoke", [sys.executable, "scripts/smoke_weather_tool.py"])

    if args.skip_rag:
        print("\nRegression checks passed. RAG eval was skipped.")
        return

    rag_command = [
        sys.executable,
        "scripts/eval_rag_quality.py",
        "--output",
        args.output,
        "--fail-under-average",
        "8",
        "--fail-under-item",
        "7",
    ]
    if args.full:
        rag_command.extend(["--eval-file", "benchmarks/gold_qa/eval_multi_doc_rag.json"])
    else:
        rag_command.extend(["--ids", args.ids])

    run_step("RAG quality eval", rag_command)
    print("\nRegression checks passed.")


if __name__ == "__main__":
    main()
