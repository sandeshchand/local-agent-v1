from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from local_agent.app.bootstrap import bootstrap_app


ROOT = Path(__file__).resolve().parents[1]


LATENCY_PROFILES: dict[str, list[str]] = {
    "sora-fast": [
        "sora_what_is",
        "sora_world_simulator",
        "sora_visual_input",
        "sora_prompt_following",
        "sora_limitations",
    ],
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


def load_eval_items(eval_path: Path, ids: str, limit: int | None) -> list[dict[str, Any]]:
    items = json.loads(eval_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError(f"Expected {eval_path} to contain a JSON list")

    selected_ids = {item.strip() for item in ids.split(",") if item.strip()}
    if selected_ids:
        items = [item for item in items if item.get("id") in selected_ids]
        missing_ids = selected_ids - {str(item.get("id")) for item in items}
        if missing_ids:
            missing = ", ".join(sorted(missing_ids))
            raise ValueError(f"Eval ids not found: {missing}")

    if limit is not None and not selected_ids:
        items = items[: max(0, limit)]
    return items


def performance_step(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("performance"):
        return response["performance"]
    for step in reversed(response.get("steps", [])):
        if step.get("type") == "performance":
            return step
    return {}


def close_dependencies(deps: Any) -> None:
    deps.sqlite_store.close()
    if deps.qdrant_store.client is not None:
        deps.qdrant_store.client.close()


def run_benchmark(
    *,
    eval_path: Path,
    output_path: Path,
    env_file: Path,
    ids: str,
    limit: int | None,
    session_prefix: str,
    warmup: bool,
    profile: str = "",
) -> dict[str, Any]:
    items = load_eval_items(eval_path, ids, limit)
    if not items:
        raise ValueError("No eval items selected for latency benchmark")

    try:
        deps = bootstrap_app(env_file)
    except Exception as exc:
        raise RuntimeError(
            f"Could not load app config from {env_file}. "
            "Create .env from .env.example or pass --env-file with a valid config."
        ) from exc
    warmup_report: dict[str, Any] | None = None
    if warmup:
        warmup_report = deps.retrieval_service.warm_up()

    report_items: list[dict[str, Any]] = []
    try:
        for index, gold in enumerate(items, start=1):
            started_at = time.perf_counter()
            response = deps.orchestrator.handle_query(
                gold["question"],
                session_id=f"{session_prefix}-{gold['id']}",
            )
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            perf = performance_step(response)
            verification = response.get("verification") or {}
            retrieval_steps = [
                step
                for step in response.get("steps", [])
                if step.get("type") == "retrieve"
            ]

            report_items.append(
                {
                    "rank": index,
                    "id": gold.get("id", ""),
                    "doc": gold.get("doc", ""),
                    "question": gold.get("question", ""),
                    "mode": response.get("mode", "unknown"),
                    "trace_id": response.get("trace_id"),
                    "total_ms": elapsed_ms,
                    "orchestrator_total_ms": perf.get("total_ms")
                    or perf.get("total_before_trace_save_ms"),
                    "trace_save_ms": perf.get("trace_save_ms"),
                    "retrieval_attempts": perf.get("retrieval_attempts", 0),
                    "tool_calls": perf.get("tool_calls", 0),
                    "citation_count": perf.get("citation_count", 0),
                    "verification_status": verification.get("status", "unknown"),
                    "evidence_paths": [step.get("evidence_path", "") for step in retrieval_steps],
                    "answer_paths": [step.get("answer_path", "") for step in retrieval_steps],
                    "timings_ms": perf.get("timings_ms", {}),
                }
            )
    finally:
        close_dependencies(deps)

    latencies = [item["total_ms"] for item in report_items]
    slowest = max(report_items, key=lambda item: item["total_ms"])
    report = {
        "eval_file": str(eval_path),
        "profile": profile,
        "count": len(report_items),
        "average_ms": round(statistics.mean(latencies), 2),
        "min_ms": round(min(latencies), 2),
        "max_ms": round(max(latencies), 2),
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "slowest": {
            "id": slowest["id"],
            "question": slowest["question"],
            "total_ms": slowest["total_ms"],
        },
        "warmup": warmup_report,
        "items": report_items,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def path_counts(reports: list[dict[str, Any]], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        for item in report.get("items", []):
            paths = item.get(field_name) or []
            if not paths:
                counts[""] = counts.get("", 0) + 1
            for path in paths:
                path_name = str(path or "")
                counts[path_name] = counts.get(path_name, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: pair[0]))


def run_repeated_benchmark(
    *,
    eval_path: Path,
    output_path: Path,
    env_file: Path,
    ids: str,
    limit: int | None,
    session_prefix: str,
    warmup: bool,
    profile: str,
    repeat: int,
) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    run_output_paths: list[Path] = []

    for run_index in range(1, repeat + 1):
        run_output_path = output_path.with_name(
            f"{output_path.stem}_run_{run_index}{output_path.suffix}"
        )
        run_output_paths.append(run_output_path)
        reports.append(
            run_benchmark(
                eval_path=eval_path,
                output_path=run_output_path,
                env_file=env_file,
                ids=ids,
                limit=limit,
                session_prefix=f"{session_prefix}-run-{run_index}",
                warmup=warmup,
                profile=profile,
            )
        )

    flattened_items: list[dict[str, Any]] = []
    for run_index, report in enumerate(reports, start=1):
        for item in report.get("items", []):
            flattened_items.append({"run": run_index, **item})

    latencies = [float(item["total_ms"]) for item in flattened_items]
    run_average_values = [float(report["average_ms"]) for report in reports]
    run_p95_values = [float(report["p95_ms"]) for report in reports]
    slowest = max(flattened_items, key=lambda item: item["total_ms"])
    run_summaries = [
        {
            "run": run_index,
            "report": str(run_output_paths[run_index - 1]),
            "average_ms": report["average_ms"],
            "p50_ms": report["p50_ms"],
            "p95_ms": report["p95_ms"],
            "slowest": report["slowest"],
            "warmup": report.get("warmup"),
        }
        for run_index, report in enumerate(reports, start=1)
    ]

    aggregate_report = {
        "eval_file": str(eval_path),
        "profile": profile,
        "repeat": repeat,
        "count": len(flattened_items),
        "queries_per_run": reports[0]["count"] if reports else 0,
        "average_ms": round(statistics.mean(latencies), 2),
        "min_ms": round(min(latencies), 2),
        "max_ms": round(max(latencies), 2),
        "p50_ms": percentile(latencies, 50),
        "p95_ms": percentile(latencies, 95),
        "slowest": {
            "run": slowest["run"],
            "id": slowest["id"],
            "question": slowest["question"],
            "total_ms": slowest["total_ms"],
        },
        "stability": {
            "run_average_min_ms": round(min(run_average_values), 2),
            "run_average_max_ms": round(max(run_average_values), 2),
            "run_average_spread_ms": round(max(run_average_values) - min(run_average_values), 2),
            "run_p95_min_ms": round(min(run_p95_values), 2),
            "run_p95_max_ms": round(max(run_p95_values), 2),
            "run_p95_spread_ms": round(max(run_p95_values) - min(run_p95_values), 2),
        },
        "evidence_path_counts": path_counts(reports, "evidence_paths"),
        "answer_path_counts": path_counts(reports, "answer_paths"),
        "runs": run_summaries,
        "items": flattened_items,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(aggregate_report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return aggregate_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark local agent latency.")
    parser.add_argument(
        "--eval-file",
        default="benchmarks/gold_qa/eval_multi_doc_rag.json",
        help="Gold QA JSON file used as benchmark input.",
    )
    parser.add_argument(
        "--output",
        default="var/logs/latency_benchmark_report.json",
        help="JSON report output path.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Environment file used to bootstrap the app.",
    )
    parser.add_argument(
        "--ids",
        default="",
        help="Comma-separated eval item ids to benchmark.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(LATENCY_PROFILES.keys()),
        default="",
        help="Named set of representative eval ids to benchmark.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of eval items to run when --ids is not provided.",
    )
    parser.add_argument(
        "--session-prefix",
        default="latency-benchmark",
        help="Session id prefix used for benchmark traces.",
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Warm retrieval dependencies before measuring query latency.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Run the selected benchmark N times and write an aggregate stability report.",
    )
    parser.add_argument(
        "--fail-over-average-ms",
        type=float,
        default=None,
        help="Exit with code 1 if average latency is above this value.",
    )
    parser.add_argument(
        "--fail-over-p95-ms",
        type=float,
        default=None,
        help="Exit with code 1 if p95 latency is above this value.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.ids and args.profile:
        print("ERROR: Use either --ids or --profile, not both.")
        sys.exit(1)
    if args.repeat < 1:
        print("ERROR: --repeat must be 1 or greater.")
        sys.exit(1)

    ids = args.ids
    if args.profile:
        ids = ",".join(LATENCY_PROFILES[args.profile])

    try:
        if args.repeat == 1:
            report = run_benchmark(
                eval_path=ROOT / args.eval_file,
                output_path=ROOT / args.output,
                env_file=ROOT / args.env_file,
                ids=ids,
                limit=args.limit,
                session_prefix=args.session_prefix,
                warmup=args.warmup,
                profile=args.profile,
            )
        else:
            report = run_repeated_benchmark(
                eval_path=ROOT / args.eval_file,
                output_path=ROOT / args.output,
                env_file=ROOT / args.env_file,
                ids=ids,
                limit=args.limit,
                session_prefix=args.session_prefix,
                warmup=args.warmup,
                profile=args.profile,
                repeat=args.repeat,
            )
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    if args.repeat == 1:
        print(f"Latency benchmark complete: {report['count']} queries")
    else:
        print(
            f"Latency stability benchmark complete: {report['repeat']} runs, "
            f"{report['count']} total queries"
        )
    print(f"Average: {report['average_ms']} ms")
    print(f"p50: {report['p50_ms']} ms")
    print(f"p95: {report['p95_ms']} ms")
    slowest_prefix = f"run {report['slowest']['run']}, " if args.repeat > 1 else ""
    print(f"Slowest: {slowest_prefix}{report['slowest']['id']} at {report['slowest']['total_ms']} ms")
    if report.get("profile"):
        print(f"Profile: {report['profile']}")
    if args.repeat > 1:
        stability = report.get("stability") or {}
        print(
            "Run p95 spread: "
            f"{stability.get('run_p95_spread_ms')} ms "
            f"({stability.get('run_p95_min_ms')} - {stability.get('run_p95_max_ms')} ms)"
        )
    if report.get("warmup"):
        warmup_ok = report["warmup"].get("ok")
        print(f"Warmup: {'ok' if warmup_ok else 'completed with errors'}")
    elif args.repeat > 1 and report.get("runs"):
        warmup_ok = all((run.get("warmup") or {}).get("ok") for run in report["runs"])
        if args.warmup:
            print(f"Warmup: {'ok' if warmup_ok else 'completed with errors'}")
    print(f"Report: {args.output}")

    failed = False
    if args.fail_over_average_ms is not None and report["average_ms"] > args.fail_over_average_ms:
        print(
            f"FAILED: average latency {report['average_ms']} ms is above "
            f"{args.fail_over_average_ms} ms"
        )
        failed = True
    if args.fail_over_p95_ms is not None and report["p95_ms"] > args.fail_over_p95_ms:
        print(
            f"FAILED: p95 latency {report['p95_ms']} ms is above "
            f"{args.fail_over_p95_ms} ms"
        )
        failed = True
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
