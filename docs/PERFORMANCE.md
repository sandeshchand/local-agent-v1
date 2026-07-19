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
venv\Scripts\python.exe scripts\benchmark_latency.py --limit 5 --output var\logs\latency_benchmark_report.json
```

Run selected questions:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --ids docker_watchtower_features,sora_world_simulator --output var\logs\latency_targeted_report.json
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

## Baseline Before Evidence Fast Path

Latest baseline command:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --limit 5 --output var\logs\latency_baseline_report.json
```

Result:

- sample size: `5` queries,
- average latency: `16527.31 ms`,
- p50 latency: `13063.21 ms`,
- p95 latency: `26323.34 ms`,
- slowest query: `sora_what_is` at `28980.54 ms`.

Trace timing showed that memory and planning are already cheap. Most time is in the retrieval action:

- evidence selection: about `7.7s` to `10.9s` per sampled query,
- answer generation: about `4.1s` to `11.1s`,
- retrieval search: normally below `300ms`, except first-run model/cache overhead.

This baseline made evidence-selection LLM work the first optimization target.

## After Evidence Fast Path

Latest command:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --limit 5 --output var\logs\latency_evidence_fast_path_report.json
```

Result:

- sample size: `5` queries,
- average latency: `5170.94 ms`,
- p50 latency: `3801.24 ms`,
- p95 latency: `8643.61 ms`,
- slowest query: `sora_what_is` at `9353.06 ms`.

Quality gate after the change:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --full --output var\logs\rag_quality_evidence_fast_path_report.json
```

Result:

- average RAG quality: `9.47/10`,
- passed: `44/45`,
- full regression passed the configured gate.

Trace timing after the change:

- evidence selection: about `1.75ms` to `2.45ms`,
- answer generation: about `2.99s` to `5.58s`,
- first-query retrieval/model warmup can still be several seconds.

Next optimization target: reduce answer-generation latency and first-query retrieval/model warmup without reducing answer quality.

## Existing Evidence Selection Optimization

An earlier baseline showed evidence selection as the slowest stage for sampled Sora questions. The first fix added a deterministic prefilter so every expanded retrieval result is not sent to the local LLM evidence judge.

The current evidence judge now uses a deterministic prefilter before LLM judging:

- keep the strongest top retrieval anchors,
- score the remaining chunks by query overlap, intent terms, retrieval score, and context role,
- send only the best candidates to the LLM judge,
- fall back to deterministic evidence ranking if the LLM judge selects nothing.

The current evidence judge also has a high-confidence deterministic fast path for supported answer shapes such as definition, list/feature, limitation, how/mechanism, why/explanation, and usage questions. If deterministic signals are not strong enough, it falls back to the LLM judge.

## Existing Answer Generation Optimization

Answer generation is also a major cost. The answer path already avoids two common sources of extra latency:

- deterministic evidence facts are built before the retrieval prompt,
- LLM fact extraction is used only when deterministic facts are empty or insufficient,
- focused rewrite is skipped when the first generated answer is already cited, focused, specific enough, and free of raw context leakage,
- retrieval prompt context is slightly tighter per chunk to reduce prompt size while keeping evidence facts and citations available.

This keeps the quality layers intact. Verification and answer repair still run after generation, and weak answers can still be rewritten or replaced by deterministic extractive answers.
