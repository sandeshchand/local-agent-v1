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
    "src/local_agent/app/cli.py",
    "src/local_agent/app/main.py",
    "src/local_agent/app/web.py",
    "src/local_agent/app/api_models.py",
    "src/local_agent/llm/ollama_client.py",
    "src/local_agent/tools/tool_registry.py",
    "src/local_agent/tools/weather_tool.py",
    "src/local_agent/tools/file_mcp.py",
    "src/local_agent/tools/sqlite_mcp.py",
    "src/local_agent/tools/mcp_adapter.py",
    "src/local_agent/evaluation/eval_candidates.py",
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
    "scripts/smoke_config.py",
    "scripts/smoke_empty_index.py",
    "scripts/smoke_sqlite_threading.py",
    "scripts/smoke_document_library.py",
    "scripts/smoke_feedback_analytics.py",
    "scripts/smoke_eval_candidates.py",
    "scripts/smoke_eval_candidate_review.py",
    "scripts/smoke_eval_candidate_run.py",
    "scripts/smoke_feedback_issue_tags.py",
    "scripts/smoke_guardrails.py",
    "scripts/smoke_file_mcp.py",
    "scripts/smoke_mcp_adapter.py",
    "scripts/smoke_sqlite_mcp.py",
    "scripts/smoke_tool_approval_ui.py",
    "scripts/smoke_weather_tool.py",
    "scripts/query_visual_world.py",
    "scripts/benchmark_latency.py",
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
        default="eval/rag_quality_regression_report.json",
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
    run_step("Config smoke", [sys.executable, "scripts/smoke_config.py"])
    run_step("Empty index smoke", [sys.executable, "scripts/smoke_empty_index.py"])
    run_step("Memory smoke", [sys.executable, "scripts/smoke_memory.py"])
    run_step("SQLite threading smoke", [sys.executable, "scripts/smoke_sqlite_threading.py"])
    run_step("Document library smoke", [sys.executable, "scripts/smoke_document_library.py"])
    run_step("Feedback analytics smoke", [sys.executable, "scripts/smoke_feedback_analytics.py"])
    run_step("Feedback eval candidate smoke", [sys.executable, "scripts/smoke_eval_candidates.py"])
    run_step("Eval candidate review smoke", [sys.executable, "scripts/smoke_eval_candidate_review.py"])
    run_step("Eval candidate run smoke", [sys.executable, "scripts/smoke_eval_candidate_run.py"])
    run_step("Feedback issue tag smoke", [sys.executable, "scripts/smoke_feedback_issue_tags.py"])
    run_step("Guardrails smoke", [sys.executable, "scripts/smoke_guardrails.py"])
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
