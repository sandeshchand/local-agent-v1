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
- Full RAG regression passed with `9.48/10` average quality and all items above the configured `7/10` item gate.
- The latest focused-list change passed smoke-only regression and targeted `ml_tsetlin_machine` quality at `9.17/10`.
- The latest CRF usage change passed targeted quality at `10.0/10`.
- The latest SmolDocling pipeline change passed targeted quality at `10.0/10`.

## First Task Tomorrow

Start with production-scale retrieval performance. The representative profile is already fast and trace metadata is now easier to read, so the next engineering task is preparing for larger document sets.

```powershell
git status --short
```

Then inspect routing and embedding hot paths:

- document routing cache,
- repeated query embedding cache,
- Qdrant local path versus server mode plan,
- latency impact under larger document counts.

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

4. Continue production readiness
   - Define scheduled/off-machine backup policy.
   - Decide authentication and user-isolation plan.
   - Keep local backup/restore as the current base.

5. MCP and guardrails next step
   - Keep File MCP and SQLite MCP read-only for now.
   - Add stronger guardrail audit visibility before enabling any write-capable tools.
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
