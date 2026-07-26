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

Run a named profile:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_representative_report.json
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

## After Representative Intent Fix

The latency benchmark now supports named profiles:

- `sora-fast`: the warmed Sora sample used during earlier fast-path work,
- `multi-doc-representative`: representative Sora, Docker, ML, Python, Pydantic, SmolDocling, and article-style questions.

The first broad run showed that performance gains were strong for Sora, but several non-Sora questions still fell into expensive LLM paths.

Representative benchmark before this fix:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_representative_report.json
```

Result:

- sample size: `12` queries,
- average latency: `9248.55 ms`,
- p50 latency: `8599.45 ms`,
- p95 latency: `20854.89 ms`,
- slowest query: `docker_lazydocker_features` at `27781.87 ms`.

Trace inspection showed two generic intent bugs:

- feature and strength questions such as `What are the key features of LazyDocker?` were being treated as definition questions,
- article questions about `starting with AI` were being treated as command/server queries because the command detector matched the word `start` too broadly.

The fix keeps true definition questions in the definition path, but routes feature, strength, formula, step, limitation, tool, type, purpose, and similar questions through the list/explanation path. It also narrows command detection to command/setup/install/run/server wording instead of any word containing `start`.

Targeted benchmark after this fix:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --ids docker_lazydocker_features,ml_tsetlin_machine,intro_three_part_formula,ai_money_starting_steps --warmup --output var\logs\latency_intent_fix_report.json
```

Result:

- sample size: `4` queries,
- average latency: `6786.09 ms`,
- p50 latency: `7006.14 ms`,
- p95 latency: `11962.25 ms`,
- `docker_lazydocker_features` improved from `27781.87 ms` to `319.82 ms`,
- `docker_lazydocker_features` now uses `answer_path=extractive_fast_path` and `evidence_path=deterministic_fast_path`.

Representative benchmark after this fix:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_intent_fix_report.json
```

Result:

- sample size: `12` queries,
- average latency: `6530.7 ms`,
- p50 latency: `6310.09 ms`,
- p95 latency: `14624.11 ms`,
- slowest query: `ai_coding_multi_agent_architecture` at `21360.92 ms`,
- answer paths: `8` extractive fast path, `2` source-window extractive replacement, `1` generic extractive fallback, `1` pipeline extractive replacement,
- evidence paths: `4` deterministic fast path, `8` LLM judge.

The next slow representative case was `ai_coding_multi_agent_architecture`, which asked what roles specialized agents can play. The evidence and answer intent layers did not yet treat role/component questions as list-style questions.

Role fast-path benchmark:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --ids ai_coding_multi_agent_architecture --warmup --output var\logs\latency_role_answer_fast_path_report.json
```

Result:

- `ai_coding_multi_agent_architecture` improved from `21360.92 ms` to `224.57 ms`,
- `evidence_path`: `deterministic_fast_path`,
- `answer_path`: `extractive_fast_path`,
- targeted RAG quality: `9.75/10`.

Representative benchmark after the role/component fast-path fix:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_role_fast_path_report.json
```

Result:

- sample size: `12` queries,
- average latency: `4698.4 ms`,
- p50 latency: `5584.24 ms`,
- p95 latency: `9945.79 ms`,
- slowest query: `ml_tsetlin_machine` at `10003.9 ms`,
- answer paths: `9` extractive fast path, `2` source-window extractive replacement, `1` pipeline extractive replacement,
- evidence paths: `5` deterministic fast path, `7` LLM judge.

Current conclusion: answer intent routing is safer and faster. Docker and role/component architecture representative questions are now fast. The remaining slow representative questions mostly use `evidence_path=llm_judge`, so the next optimization should improve deterministic evidence coverage for ML, Python, and article-style questions.

## After Strengths Fast Path

The next slow representative case was `ml_tsetlin_machine`, which asks for key strengths. The answer path was already extractive, but evidence selection still used the LLM judge because strengths/advantages/benefits were not recognized as list-style evidence.

Strength fast-path benchmark:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --ids ml_tsetlin_machine --warmup --output var\logs\latency_strength_fast_path_report.json
```

Result:

- first measured run: `5604.14 ms`,
- repeated measured run: `1641.24 ms`,
- `evidence_path`: `deterministic_fast_path`,
- `answer_path`: `extractive_fast_path`,
- targeted RAG quality: `9.17/10`.

Representative benchmark after the strengths fast-path fix:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_strength_fast_path_report.json
```

Result:

- sample size: `12` queries,
- average latency: `3649.45 ms`,
- p50 latency: `2992.74 ms`,
- p95 latency: `8428.04 ms`,
- slowest query: `python_large_numbers` at `9122.65 ms`,
- answer paths: `10` extractive fast path, `1` source-window extractive replacement, `1` pipeline extractive replacement,
- evidence paths: `6` deterministic fast path, `6` LLM judge.

Current conclusion: strengths/advantages/benefits are now handled as generic list-style evidence. The next slow representative queries still use `evidence_path=llm_judge`; start with `python_large_numbers`, then inspect Pydantic purpose, AI side-hustle steps, Python HTTP server, CRFs, and introduction formula.

## After Large-Integer Fast Path

The next slow representative case was `python_large_numbers`. Evidence selection already recognized it as a mechanism query, but deterministic evidence was missing large-number markers and the source-window answer was rejected because surrounding code-heavy context made it look under-specific.

Large-integer benchmark:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --ids python_large_numbers --warmup --output var\logs\latency_large_integer_answer_fast_path_report.json
```

Result:

- `python_large_numbers` improved from `9122.65 ms` to `183.18 ms`,
- broad-profile rerun measured it at `150.15 ms`,
- `evidence_path`: `deterministic_fast_path`,
- `answer_path`: `extractive_fast_path`,
- targeted RAG quality: `10.0/10`.

Representative benchmark after the large-integer fast-path fix:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_large_integer_fast_path_report.json
```

Result:

- sample size: `12` queries,
- average latency: `3618.91 ms`,
- p50 latency: `3491.15 ms`,
- p95 latency: `8501.83 ms`,
- slowest query: `intro_three_part_formula` at `9674.45 ms`,
- answer paths: `10` extractive fast path, `1` pipeline extractive replacement, `1` source-window extractive replacement,
- evidence paths: `7` deterministic fast path, `5` LLM judge.

Current conclusion: large-number/integer mechanism questions now have generic deterministic evidence and focused extractive answering. The next slow representative queries still use `evidence_path=llm_judge`; start with `intro_three_part_formula`, then inspect Pydantic purpose, AI side-hustle steps, Python HTTP server, and CRFs.

## After Formula Fast Path

The next slow representative case was `intro_three_part_formula`. The answer extractor already had a generic formula window, but evidence selection classified `What is the article's three-part formula...` as a definition question before it could reach list-style evidence handling.

The fix treats formula and part-formula questions as list-shaped evidence, adds generic formula component markers to deterministic evidence scoring, and allows high-confidence formula answers to skip normal LLM generation when the candidate contains structured formula components.

Formula benchmark:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --ids intro_three_part_formula --warmup --output var\logs\latency_formula_fast_path_report.json
```

Result:

- `intro_three_part_formula` improved from `9674.45 ms` to `255.41 ms`,
- broad-profile rerun measured it at `165.34 ms`,
- `evidence_path`: `deterministic_fast_path`,
- `answer_path`: `extractive_fast_path`,
- targeted RAG quality: `9.5/10`.

Representative benchmark after the formula fast-path fix:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_formula_fast_path_report.json
```

Result:

- sample size: `12` queries,
- average latency: `2805.31 ms`,
- p50 latency: `1158.23 ms`,
- p95 latency: `7027.56 ms`,
- slowest query: `pydantic_env_file_purpose` at `7100.35 ms`,
- answer paths: `11` extractive fast path, `1` pipeline extractive replacement,
- evidence paths: `8` deterministic fast path, `4` LLM judge.

Current conclusion: formula/list-style article questions now avoid LLM evidence judging and answer generation when the retrieved evidence already contains the numbered components. The next slow representative queries still use `evidence_path=llm_judge`; start with `pydantic_env_file_purpose`, then inspect AI side-hustle steps, Python HTTP server, and CRFs.

## After Config-Purpose Fast Path

The next slow representative case was `pydantic_env_file_purpose`. The answer path already used the `.env` config-purpose extractor, but evidence selection still used the LLM judge because explanation directness did not recognize config-purpose signals such as local development, environment variables, secrets, API keys, database URLs, tokens, slow setup, and key-value config files.

The fix adds generic config-purpose markers to deterministic evidence scoring and intent terms. It also narrows answer punctuation cleanup so file names such as `.env` keep their leading space instead of becoming `The.env` or `A.env`.

Config-purpose benchmark:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --ids pydantic_env_file_purpose --warmup --output var\logs\latency_pydantic_env_fast_path_report.json
```

Result:

- `pydantic_env_file_purpose` improved from `7100.35 ms` to `254.3 ms`,
- broad-profile rerun measured it at `214.22 ms`,
- `evidence_path`: `deterministic_fast_path`,
- `answer_path`: `extractive_fast_path`,
- targeted RAG quality: `10.0/10`.

Representative benchmark after the config-purpose fast-path fix:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_pydantic_env_fast_path_report.json
```

Result:

- sample size: `12` queries,
- average latency: `2246.97 ms`,
- p50 latency: `245.74 ms`,
- p95 latency: `6394.89 ms`,
- slowest query: `ai_money_starting_steps` at `6994.95 ms`,
- answer paths: `11` extractive fast path, `1` pipeline extractive replacement,
- evidence paths: `9` deterministic fast path, `3` LLM judge.

Current conclusion: config/secrets/local-development purpose questions now avoid LLM evidence judging when retrieved evidence contains direct purpose signals. The next slow representative queries still use `evidence_path=llm_judge`; start with `ai_money_starting_steps`, then inspect Python HTTP server command usefulness and CRF usage.

## After Recommended-Steps Fast Path

The next slow representative case was `ai_money_starting_steps`. Retrieval already found the right chunk and answer generation already used the extractive list path, but deterministic evidence selection rejected the fast path because a single numbered list did not score as direct enough.

The fix is generic: list-shaped questions now give directness credit to numbered list items and common recommendation/start phrasing such as "first steps", "do this first", "start today", "here's how", and "recommended". This helps article and guide-style PDFs where the answer is a compact numbered action list.

Recommended-steps benchmark:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --ids ai_money_starting_steps --warmup --output var\logs\latency_ai_money_steps_fast_path_report.json
```

Result:

- `ai_money_starting_steps` improved from `6994.95 ms` to `172.83 ms`,
- broad-profile rerun measured it at `159.54 ms`,
- `evidence_path`: `deterministic_fast_path`,
- `answer_path`: `extractive_fast_path`,
- targeted RAG quality: `9.5/10`.

Representative benchmark after the recommended-steps fast-path fix:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_ai_money_steps_fast_path_report.json
```

Result:

- sample size: `12` queries,
- average latency: `1686.67 ms`,
- p50 latency: `206.93 ms`,
- p95 latency: `5961.88 ms`,
- slowest query: `python_builtin_http_server` at `6530.99 ms`,
- answer paths: `11` extractive fast path, `1` pipeline extractive replacement,
- evidence paths: `10` deterministic fast path, `2` LLM judge.

Current conclusion: guide-style numbered recommendation lists now avoid LLM evidence judging. The next slow representative queries still use `evidence_path=llm_judge`; start with Python HTTP server command usefulness, then inspect CRF usage.

## After Command-Usefulness Fast Path

The next slow representative case was `python_builtin_http_server`. Answer generation already used the command extractor, but evidence selection did not classify command/usefulness questions as a deterministic evidence shape.

The fix treats command questions that ask why a command is useful as usage-shaped evidence. It adds generic command-usefulness markers such as single command, built-in web server, quickly test, share files, local network, browser, localhost, and third-party tools. This is meant for command/setup guides in any document family, not only Python articles.

Command-usefulness benchmark:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --ids python_builtin_http_server --warmup --output var\logs\latency_python_http_server_fast_path_report.json
```

Result:

- `python_builtin_http_server` improved from `6530.99 ms` to `260.17 ms`,
- broad-profile rerun measured it at `195.97 ms`,
- `evidence_path`: `deterministic_fast_path`,
- `answer_path`: `extractive_fast_path`,
- targeted RAG quality: `9.5/10`.

Representative benchmark after the command-usefulness fast-path fix:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_python_http_server_fast_path_report.json
```

Result:

- sample size: `12` queries,
- average latency: `1292.09 ms`,
- p50 latency: `220.23 ms`,
- p95 latency: `5597.91 ms`,
- slowest query: `ml_tsetlin_machine` at `6142.94 ms`,
- answer paths: `11` extractive fast path, `1` pipeline extractive replacement,
- evidence paths: `11` deterministic fast path, `1` LLM judge.

Current conclusion: command-usefulness questions now avoid LLM evidence judging. The next slow representative case is `ml_tsetlin_machine`, which already uses deterministic evidence and extractive answering, so inspect retrieval/reranker timing before changing answer behavior. Also inspect `ml_crfs`, the remaining representative `evidence_path=llm_judge` case.

## After Focused List Topic Filter

The `ml_tsetlin_machine` trace showed that retrieval and extractive answer generation were already fast, but the first list answer mixed neighboring sections such as Symbolic Regression and Random Kitchen Sinks into the Tsetlin answer. Verification correctly rejected that mixed-topic answer, and LLM answer repair added most of the latency.

The fix keeps focused list questions generic: when a query names a focus entity, the list extractor now filters competing named-topic facts, keeps section follow-up facts only when they read like details of the focused entity, and uses an entity-specific prefix for feature, strength, role, and component answers. The high-confidence answer gate also rejects focused feature/list candidates that introduce a separate named topic, so source-window candidates can fall through to stricter extractive list answers. A synthetic focused-list smoke test was added to regression coverage.

Focused-list benchmark:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --ids ml_tsetlin_machine --warmup --output var\logs\latency_tsetlin_focused_list_final_report.json
```

Result:

- `ml_tsetlin_machine` improved from `2859.2 ms` in the pre-fix rerun to `211.38 ms`,
- broad-profile rerun measured it at `193.14 ms`,
- `evidence_path`: `deterministic_fast_path`,
- `answer_path`: `extractive_fast_path`,
- verification passed without `answer_repair`,
- targeted RAG quality: `9.17/10`.

Representative benchmark after the focused-list topic filter:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_focused_list_final_report.json
```

Result:

- sample size: `12` queries,
- average latency: `742.0 ms`,
- p50 latency: `196.03 ms`,
- p95 latency: `3320.76 ms`,
- slowest query: `ml_crfs` at `5462.98 ms`,
- next deterministic-but-slow query: `smoldocling_app_pipeline` at `1568.04 ms`,
- answer paths: `11` extractive fast path, `1` pipeline extractive replacement,
- evidence paths: `11` deterministic fast path, `1` LLM judge.

Current conclusion: focused entity list answers now avoid slow repair when neighboring chunks mention other named topics. The next slow case is `ml_crfs`, the remaining representative `evidence_path=llm_judge` item. After that, inspect `smoldocling_app_pipeline`, which is deterministic evidence but still slow due to the replacement path.

## After Technical Usage Fast Path

The `ml_crfs` trace showed that answer generation was already extractive, but evidence selection still used the LLM judge for a technical "used for" question. The fast path detected the query shape as `usage`, but the deterministic sufficiency check did not recognize structured-prediction, sequential-data, context, label, and NER signals as usage evidence.

The fix extends generic technical usage evidence markers and intent terms. It also improves the used-for extractor so code-heavy example snippets are converted into a clean cited application fact, for example `NER-like format`, instead of leaking imports into the answer.

Technical-usage benchmark:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --ids ml_crfs --warmup --output var\logs\latency_ml_crfs_usage_fast_path_report.json
```

Result:

- `ml_crfs` improved from `5462.98 ms` in the previous representative run to `259.47 ms`,
- broad-profile rerun measured it at `195.31 ms`,
- `evidence_path`: `deterministic_fast_path`,
- `answer_path`: `extractive_fast_path`,
- verification passed without repair,
- targeted RAG quality: `10.0/10`.

Representative benchmark after the technical usage fast path:

```powershell
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_ml_crfs_usage_fast_path_report.json
```

Result:

- sample size: `12` queries,
- average latency: `588.94 ms`,
- p50 latency: `192.36 ms`,
- p95 latency: `2365.39 ms`,
- slowest query: `smoldocling_app_pipeline` at `4971.18 ms`,
- answer paths: `11` extractive fast path, `1` pipeline extractive replacement,
- evidence paths: `12` deterministic fast path.

Current conclusion: every representative query now avoids LLM evidence judging. The next slow case is `smoldocling_app_pipeline`, which has deterministic evidence but still uses the slower pipeline replacement path.

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
