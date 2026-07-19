from __future__ import annotations

import tempfile
from pathlib import Path

from local_agent.evaluation.memory_eval import run_memory_eval


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "memory_quality_report.json"
        report = run_memory_eval(
            "benchmarks/memory/memory_multi_turn.json",
            output_path,
        )

    assert report["average_score"] >= 9.0
    assert report["pass_count"] == report["total_count"]

    sensitive = next(item for item in report["items"] if item["id"] == "sensitive_short_term_redaction")
    assert not sensitive["triggered_must_not_include"]
    assert not sensitive["triggered_forbidden_kinds"]

    print("Memory eval smoke test passed.")


if __name__ == "__main__":
    main()
