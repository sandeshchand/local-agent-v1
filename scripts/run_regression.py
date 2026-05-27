from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

COMPILE_TARGETS = [
    "agent/orchestrator.py",
    "agent/planner.py",
    "agent/guardrails.py",
    "agent/schemas.py",
    "app/bootstrap.py",
    "app/cli.py",
    "app/main.py",
    "app/web.py",
    "app/api_models.py",
    "app/eval_candidates.py",
    "app/tool_registry.py",
    "app/weather_tool.py",
    "retrieval/answer_service.py",
    "storage/sqlite_store.py",
    "scripts/smoke_memory.py",
    "scripts/smoke_sqlite_threading.py",
    "scripts/smoke_feedback_analytics.py",
    "scripts/smoke_eval_candidates.py",
    "scripts/smoke_feedback_issue_tags.py",
    "scripts/smoke_guardrails.py",
    "scripts/smoke_weather_tool.py",
    "scripts/eval_rag_quality.py",
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
    run_step("Memory smoke", [sys.executable, "scripts/smoke_memory.py"])
    run_step("SQLite threading smoke", [sys.executable, "scripts/smoke_sqlite_threading.py"])
    run_step("Feedback analytics smoke", [sys.executable, "scripts/smoke_feedback_analytics.py"])
    run_step("Feedback eval candidate smoke", [sys.executable, "scripts/smoke_eval_candidates.py"])
    run_step("Feedback issue tag smoke", [sys.executable, "scripts/smoke_feedback_issue_tags.py"])
    run_step("Guardrails smoke", [sys.executable, "scripts/smoke_guardrails.py"])
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
        rag_command.extend(["--eval-file", "test/eval_multi_doc_rag.json"])
    else:
        rag_command.extend(["--ids", args.ids])

    run_step("RAG quality eval", rag_command)
    print("\nRegression checks passed.")


if __name__ == "__main__":
    main()
