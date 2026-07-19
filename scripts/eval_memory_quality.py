from __future__ import annotations

import argparse
import sys
from pathlib import Path

from local_agent.evaluation.memory_eval import run_memory_eval


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate memory retrieval and safety behavior.")
    parser.add_argument("--eval-file", default="benchmarks/memory/memory_multi_turn.json")
    parser.add_argument("--output", default="var/logs/memory_quality_report.json")
    parser.add_argument(
        "--fail-under-average",
        type=float,
        default=None,
        help="Exit with code 1 when the average score is below this value.",
    )
    parser.add_argument(
        "--fail-under-item",
        type=float,
        default=None,
        help="Exit with code 1 when any individual item score is below this value.",
    )
    args = parser.parse_args()

    report = run_memory_eval(Path(args.eval_file), Path(args.output))
    print(f"Average memory quality score: {report['average_score']}/10")
    print(f"Passed: {report['pass_count']}/{report['total_count']} at >= {report['pass_threshold']}/10")

    failed = False
    for item in report["items"]:
        print(f"{item['id']}: {item['score']}/10")
        if item["missing_must_include"]:
            print(f"  missing: {item['missing_must_include']}")
        if item["triggered_must_not_include"]:
            print(f"  unsafe: {item['triggered_must_not_include']}")
        if item["missing_required_kinds"]:
            print(f"  missing kinds: {item['missing_required_kinds']}")
        if item["triggered_forbidden_kinds"]:
            print(f"  forbidden kinds: {item['triggered_forbidden_kinds']}")

    if args.fail_under_average is not None and report["average_score"] < args.fail_under_average:
        print(
            f"FAILED: average score {report['average_score']}/10 is below "
            f"{args.fail_under_average}/10"
        )
        failed = True

    if args.fail_under_item is not None:
        low_items = [
            item
            for item in report["items"]
            if item["score"] < args.fail_under_item
        ]
        if low_items:
            failed_ids = ", ".join(item["id"] for item in low_items)
            print(f"FAILED: these items are below {args.fail_under_item}/10: {failed_ids}")
            failed = True

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
