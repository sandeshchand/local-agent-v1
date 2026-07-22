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

Retrieval steps also include decision-path fields:

- `evidence_path`,
- `answer_path`,
- `evidence_trace`,
- `answer_trace`.

These explain whether evidence selection used the deterministic fast path, LLM judging, or heuristic fallback, and whether answering used the extractive fast path, normal LLM generation, or a deterministic replacement.

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
venv\Scripts\python.exe scripts\benchmark_latency.py --limit 5 --warmup --output var\logs\latency_benchmark_report.json
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
- per-query `evidence_paths`,
- per-query `answer_paths`,
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
2. Inspect `answer_path` and `evidence_path` before changing behavior.
3. Reduce unnecessary normal LLM answer generation where trace rejection reasons show a safe generic fix.
4. Tune reranker candidate count only if reranking remains slow after warmup.
5. Cache repeated document routing and embedding work.
6. Move Qdrant from local path mode to server mode for larger collections.
7. Add ingestion batching and parallel parsing for large PDF sets.

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

This made answer generation the next optimization target.

## After Answer Generation Fast Path

Latest command:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --limit 5 --output var\logs\latency_answer_generation_fast_path_final_report.json
```

Result:

- sample size: `5` queries,
- average latency: `2208.78 ms`,
- p50 latency: `237.74 ms`,
- p95 latency: `8155.22 ms`,
- slowest query: `sora_what_is` at `10132.03 ms`.

Quality gate after the change:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --full --output var\logs\rag_quality_answer_generation_fast_path_final2_report.json
```

Result:

- average RAG quality: `9.39/10`,
- passed: `44/45` at `>= 8/10`,
- no item fell below the configured `7/10` item gate,
- full regression passed.

Trace timing after the change:

- evidence selection: about `1.85ms` to `2.94ms`,
- fast-path answer generation for four sampled Sora questions: about `6.78ms` to `19.99ms`,
- `sora_what_is` still uses normal LLM generation and first-query retrieval/model warmup.

This made retrieval/model warmup and the remaining definition path the next optimization target.

## After Retrieval Warmup And Definition Fast Path

Latest warmup benchmark command:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --limit 5 --warmup --output var\logs\latency_retrieval_definition_warmup_final_report.json
```

Result:

- sample size: `5` queries,
- average latency: `1694.8 ms`,
- p50 latency: `240.19 ms`,
- p95 latency: `6054.57 ms`,
- slowest query: `sora_prompt_following` at `7504.51 ms`,
- retrieval warmup completed successfully.

The best repeated warmed sample was:

- average latency: `199.51 ms`,
- p50 latency: `196.27 ms`,
- p95 latency: `209.59 ms`,
- slowest query: `sora_visual_input` at `210.24 ms`.

Quality gate after the change:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --full --output var\logs\rag_quality_retrieval_definition_warmup_final_report.json
```

Result:

- average RAG quality: `9.51/10`,
- passed: `45/45` at `>= 8/10`,
- full regression passed.

Warmup details from the final benchmark:

- Qdrant collection check: `0.03 ms`,
- embedding model warmup: `51.39 ms`,
- reranker model warmup: `4307.71 ms`.

Trace timing after the change:

- retrieval search stayed around `171ms` to `190ms` in the final five-query sample,
- evidence selection stayed around `1.85ms` to `3.59ms`,
- high-confidence extractive answers took about `8.88ms` to `20.18ms`,
- one harder prompt-following question used normal LLM answer generation and took `7279.87ms`.

Current conclusion: retrieval/model warmup is now handled. The remaining latency variance comes from questions that correctly fall back to normal LLM answer generation instead of the deterministic fast path.

This made fast-path observability the next optimization target.

## After Fast-Path Observability

The orchestrator now stores path metadata inside each retrieval step:

```text
evidence_path
answer_path
evidence_trace
answer_trace
```

The latency benchmark also writes `evidence_paths` and `answer_paths` per query.

Useful examples:

- `evidence_path=deterministic_fast_path`: evidence did not require LLM judging.
- `evidence_path=llm_judge`: evidence selection used the local chat model.
- `evidence_path=heuristic_fallback_after_llm`: LLM judging selected no evidence, so deterministic fallback selected the context.
- `answer_path=extractive_fast_path`: answer returned before LLM generation.
- `answer_path=llm_generation`: answer came from the normal retrieval prompt.
- `answer_path=definition_extractive_replacement`: LLM was called, but a stronger deterministic definition answer replaced it.

`answer_trace.fast_path.rejections` records generic rejection reasons for skipped fast-path candidates. This is the next debugging tool for latency work: slow answers can now show whether the answer was slow because the query shape was unsupported, the candidate was under-specific, citations were missing, or normal LLM generation was genuinely needed.

This made the low-value candidate filter the next optimization target, because a slow prompt-following trace showed a valid mechanism answer was rejected for `low_value_candidate_items`.

## After Low-Value Fast-Path Fix

The low-value filter was narrowed so article/social metadata is still rejected, but valid technical terms and phrases are not rejected accidentally:

- `DALL-E`-style names are allowed,
- `prompt following` is allowed,
- social metadata such as follower/following counts, publication prompts, and read-time fragments is still rejected.

Slow-case benchmark:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --ids sora_prompt_following --warmup --output var\logs\latency_prompt_following_low_value_fix_report.json
```

Result:

- `sora_prompt_following`: `215.95 ms`,
- `evidence_path`: `deterministic_fast_path`,
- `answer_path`: `extractive_fast_path`,
- `used_llm_generation`: `false`.

Five-query warmed benchmark:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --limit 5 --warmup --output var\logs\latency_low_value_fast_path_fix_report.json
```

Result:

- average latency: `227.06 ms`,
- p50 latency: `221.36 ms`,
- p95 latency: `248.38 ms`,
- slowest query: `sora_what_is` at `251.32 ms`.

Quality gates:

- targeted RAG: `9.06/10`, `3/3` at `>= 8/10`,
- full RAG: `9.48/10`, passed the configured gate,
- targeted rerun for `sora_limitations`: `9.75/10`.

Current conclusion: the first five warmed Sora questions now avoid normal LLM answer generation. The next performance task should run a broader latency benchmark across more document families and fix only repeated generic rejection patterns.

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

- high-confidence extractive answers can return before LLM generation,
- deterministic evidence facts are built before the retrieval prompt,
- LLM fact extraction is used only when deterministic facts are empty or insufficient,
- focused rewrite is skipped when the first generated answer is already cited, focused, specific enough, and free of raw context leakage,
- retrieval prompt context is slightly tighter per chunk to reduce prompt size while keeping evidence facts and citations available.

This keeps the quality layers intact. Verification and answer repair still run after generation, and weak answers can still be rewritten or replaced by deterministic extractive answers.
