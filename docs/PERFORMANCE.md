# Performance Measurement

This project should improve speed with measurement first. We should not guess where the RAG system is slow; each answer trace now records timing so we can see the expensive stage.

## What Was Added

Each orchestrator response now includes a final `performance` step.

The step records:

- memory load time,
- planning time,
- full action time,
- assistant memory save time,
- retrieval attempt count,
- tool-call count,
- citation count,
- total time before trace save.

Retrieval steps also include detailed timings:

- document routing,
- retrieval search,
- evidence selection,
- context merge,
- answer generation.

Verification, guardrail, direct-answer, and tool-call steps also include timing fields where useful.

## Why This Matters

For production work, quality and latency must be improved together.

Example:

- If `retrieval_search_ms` is high, optimize Qdrant, embeddings, reranking, or candidate count.
- If `answer_generation_ms` is high, optimize prompt size, context size, or model choice.
- If `planning_ms` is high, simplify planner routing or use a smaller model for planning.
- If `memory_load_ms` is high, optimize SQLite queries or memory limits.

This avoids changing the whole system blindly.

## Benchmark Command

Run a quick latency benchmark:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --limit 5 --output eval\latency_benchmark_report.json
```

Run selected questions:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --ids docker_watchtower_features,sora_world_simulator --output eval\latency_targeted_report.json
```

Use a specific environment file:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --limit 5
```

The benchmark needs the same valid `.env` used by the app. If `.env` is missing, create it from `.env.example` and point `SQLITE_PATH` and `QDRANT_PATH` to the indexed runtime data you want to test.

Add optional thresholds:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --limit 5 --fail-over-average-ms 30000 --fail-over-p95-ms 45000
```

The script writes a JSON report with:

- average latency,
- p50 latency,
- p95 latency,
- slowest query,
- per-query timings,
- trace IDs for inspection in the UI.

## Recommended Changing Process

Use this process whenever improving performance:

1. Run the latency benchmark and save the report.
2. Open the slowest trace in the UI.
3. Check the `performance` step and retrieval `timings_ms`.
4. Identify the slowest stage.
5. Make one focused optimization.
6. Run quality regression to confirm answers did not get worse.
7. Run latency benchmark again and compare the new report with the old one.

This is the safe production pattern: baseline, change one thing, re-measure.

## Current Optimization Order

Recommended order for future performance improvements:

1. Measure latency with `scripts/benchmark_latency.py`.
2. Reduce unnecessary LLM calls in planner and evidence selection.
3. Tune reranker candidate count.
4. Cache repeated document routing and embedding work.
5. Move Qdrant from local path mode to server mode for larger collections.
6. Add ingestion batching and parallel parsing for large PDF sets.

Do not optimize by removing verification or answer repair first. Those protect answer quality.
