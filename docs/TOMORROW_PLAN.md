# Tomorrow Plan

Use this note to restart the next development session without losing the thread.

## Current State

The latest work moved the project closer to production readiness and improved RAG latency without weakening answer quality.

- Added local deployment documentation in `docs/DEPLOYMENT.md`.
- Added a high-confidence fast path in `EvidenceJudge`.
- Evidence selection now takes around 2ms on the sampled Sora queries.
- Added a high-confidence answer-generation fast path in `AnswerService`.
- Added retrieval/model warmup for Qdrant collection checks, query embeddings, and the cross-encoder reranker.
- Added a safer definition fast path and low-value candidate rejection for noisy extracted bullets.
- Added fast-path observability for evidence and answer decisions in retrieval traces.
- Narrowed low-value metadata filtering so terms like `prompt following` and technical names with punctuation are not rejected as social metadata.
- Added named latency benchmark profiles for Sora-only and multi-document representative samples.
- Found a broad-profile slow case where feature questions were treated as definition questions.
- Fixed answer intent routing so feature, strength, formula, step, limitation, tool, type, and purpose questions are not forced into the definition path.
- Tightened command intent routing so article questions about `starting with AI` are not treated as shell/server command questions.
- Five-query latency improved from `16527.31 ms` average to `5170.94 ms` after evidence fast path, then to `2208.78 ms` after answer fast path.
- Warmed retrieval produced a best five-query sample of `199.51 ms` average and a latest repeated sample of `1694.8 ms` average because one harder answer still used normal LLM generation.
- The latest warmed five-query sample is `227.06 ms` average with `248.38 ms` p95.
- A targeted intent-fix benchmark reduced `docker_lazydocker_features` from `27781.87 ms` to `319.82 ms`.
- The broad representative profile improved from `9248.55 ms` average to `6530.7 ms` average after the intent fix.
- The role/component fast-path fix reduced `ai_coding_multi_agent_architecture` from `21360.92 ms` to `224.57 ms`.
- The broad representative profile improved again to `4698.4 ms` average with `9945.79 ms` p95.
- The strengths fast-path fix moved `ml_tsetlin_machine` to deterministic evidence and extractive answer paths.
- The broad representative profile improved again to `3649.45 ms` average with `8428.04 ms` p95.
- The large-integer fast-path fix reduced `python_large_numbers` from `9122.65 ms` to `183.18 ms`.
- The formula fast-path fix reduced `intro_three_part_formula` from `9674.45 ms` to `255.41 ms`.
- The config-purpose fast-path fix reduced `pydantic_env_file_purpose` from `7100.35 ms` to `254.3 ms`.
- The recommended-steps fast-path fix reduced `ai_money_starting_steps` from `6994.95 ms` to `172.83 ms`.
- The command-usefulness fast-path fix reduced `python_builtin_http_server` from `6530.99 ms` to `260.17 ms`.
- The focused-list topic filter reduced `ml_tsetlin_machine` from `2859.2 ms` in the pre-fix rerun to `211.38 ms`.
- The technical-usage fast path reduced `ml_crfs` from `5462.98 ms` to `259.47 ms`.
- The pipeline fast path reduced `smoldocling_app_pipeline` from `4971.18 ms` to `204.28 ms`.
- The broad representative profile is now `190.57 ms` average with `220.62 ms` p95.
- The repeated representative profile is `200.67 ms` average with `226.45 ms` p95 across `3` runs and `36` total queries.
- The repeated profile p95 spread is `16.06 ms`.
- All `12` representative queries now use deterministic evidence selection.
- All `12` representative queries now use extractive answer fast paths.
- The current slowest broad-profile case is `sora_prompt_following` at `230.65 ms`.
- Trace UI summaries now show compact evidence path, answer path, evidence shape, accepted fast-path source, and rejected candidate reasons.
- Added v1 document-routing cache with SQLite signature invalidation.
- Added v1 repeated-query embedding cache in the Ollama embedding client.
- Added generic recommended-item extraction for questions such as `which tools does the article recommend`.
- Added generic setup/run command-sequence extraction for tutorial PDFs.
- Added high-confidence coverage checks for focused lists and limitation lists to avoid unnecessary LLM fallback.
- Full RAG regression passed with `9.52/10` average quality and all items above the configured `7/10` item gate.
- The final repeated representative profile is `199.46 ms` average with `237.07 ms` p95 across `3` runs and `36` total queries.
- The latest focused-list change passed smoke-only regression and targeted `ml_tsetlin_machine` quality at `9.17/10`.
- The latest CRF usage change passed targeted quality at `10.0/10`.
- The latest SmolDocling pipeline change passed targeted quality at `10.0/10`.
- Added production-scale retrieval profiling in `scripts/profile_retrieval_scale.py`.
- Added Qdrant server-mode planning documentation.
- Added versioned incremental ingestion with parser/chunking metadata.
- Added safe re-ingestion cleanup for stale Qdrant vectors by `doc_id`.
- Added ingestion status visibility in CLI, API, and the UI `Ingest` workspace tab.
- Added gold QA coverage auditing with `scripts/audit_gold_qa_coverage.py`.
- Added backup listing and retention pruning with dry-run by default.
- Added optional API token auth for `/api/*`.
- Added request session isolation for traces, feedback, memory, and tool audit.
- Added a UI `Access` panel for token/session settings.
- Added stronger guardrail audit visibility with risk labels, blocked-action counts, and write/delete category highlighting.
- Added guardrail path-policy checks for File MCP tools before execution.

## First Task Tomorrow

Start by checking the branch and pushing any local commit that is not on GitHub yet.

```powershell
git status --short
git log --oneline origin/dev..dev
```

Latest completed work:

- Production-scale retrieval performance validation is available through `scripts/profile_retrieval_scale.py`.
- Ingestion is safer for daily document batches through incremental skip behavior, `--force` rebuilds, version metadata, Qdrant cleanup, and ingestion status visibility.
- Added `scripts/audit_gold_qa_coverage.py` to compare indexed SQLite documents, raw PDFs, and gold QA items.
- Added `scripts/smoke_gold_qa_coverage.py` for deterministic coverage-audit smoke testing.
- Added the coverage smoke test to `scripts/run_regression.py`.
- Added workflow documentation in `docs/GOLD_QA_COVERAGE.md` and `docs/EVALUATION.md`.
- Added `list-backups` and `prune-backups` operations for local runtime backup retention.
- Added `AUTH_ENABLED` / `AUTH_TOKEN` config.
- Added `docs/AUTHENTICATION.md`.
- Added `scripts/smoke_auth.py`.

First validation tomorrow:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
venv\Scripts\python.exe scripts\smoke_auth.py
venv\Scripts\python.exe scripts\audit_gold_qa_coverage.py --env-file .env --output var\logs\gold_qa_coverage_report.json
```

Then test the UI manually:

- start the web app with `scripts\start_web.ps1`,
- open the `Access` panel,
- save a session id,
- ask one question,
- confirm traces, feedback, memory, and tool audit still load,
- optionally set `AUTH_ENABLED=true` with a test token and confirm API calls require that token.

Recommended next implementation:

- add stronger write/delete policy before enabling any write-capable File MCP tools,
- or design production user accounts and per-user document/index isolation.

Do not add more answer fast paths unless a new eval or trace shows a repeated generic failure pattern.

## Recommended Feature Order

1. Broaden latency coverage across document families
   - Repeat the representative profile with `--repeat 3` after performance-sensitive changes.
   - Add only generic fixes for repeated safe rejection patterns across multiple document families.
   - Re-run `--profile multi-doc-representative` after each change.
   - Tighten prompt/context only when trace data shows the prompt is larger than needed.
   - Consider chat-model warmup for demos or local production startup.

2. Improve trace UI summaries
   - Done for evidence path, answer path, evidence shape, accepted fast-path source, and rejection reasons.
   - Next UI work should come from user feedback after testing the new trace cards.

3. Broaden gold QA for new PDFs
   - Add more questions from unseen PDFs, daily medium-style articles, arXiv papers, and technical blog PDFs.
   - Keep every benchmark generic; do not add document-specific hardcoded keywords.
   - Add 3 to 5 QA items for each important new document family.
   - Run focused RAG eval after adding each batch.

4. Continue production readiness
   - Done: local backup retention controls.
   - Done: API token auth v1.
   - Done: request session isolation for traces, feedback, memory, and tool audit.
   - Next: scheduled/off-machine backup execution.
   - Next: production user accounts and per-user document/index isolation.

5. MCP and guardrails next step
   - Keep File MCP and SQLite MCP read-only for now.
   - Done: stronger guardrail audit visibility before enabling any write-capable tools.
   - Done: explicit path policy before writable File MCP tools.
   - Next: add stronger write/delete policy before writable File MCP tools.
   - Plan true external MCP transport only when there is a concrete tool use case.

## Validation Commands

Run the smoke checks first:

```powershell
venv\Scripts\python.exe scripts\smoke_evidence_prefilter.py
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```

For answering, retrieval, or ranking changes:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --full --output var\logs\rag_quality_report.json
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --limit 5 --warmup --output var\logs\latency_after_change_report.json
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --repeat 3 --output var\logs\latency_multi_doc_after_change_report.json
```

## Important Reminders

- Stop the web server before full local RAG evals if Qdrant path locking appears.
- Put generated reports in `var\logs`.
- Keep the system general-purpose for many unseen PDFs.
- Do not add hardcoded PDF-specific keywords.
