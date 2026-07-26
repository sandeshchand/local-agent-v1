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
- The current slowest broad-profile case is `python_large_numbers` at `9122.65 ms`, with `evidence_path=llm_judge`.
- Full RAG regression passed with `9.48/10` average quality and all items above the configured `7/10` item gate.
- The latest changes are still uncommitted.

## First Task Tomorrow

Commit today's validated broad latency and intent-routing work before starting new behavior.

```powershell
git status --short
git add -A
git commit -m "perf: add broad latency profile and intent fixes"
```

After that, push and merge only if the branch still looks clean.

## Recommended Feature Order

1. Broaden latency coverage across document families
   - Inspect the latest slow traces that still use `evidence_path=llm_judge`.
   - Start with `python_large_numbers`, then compare Pydantic purpose, AI side-hustle steps, Python HTTP server, CRFs, and introduction formula.
   - Look for a generic evidence fast-path rule, such as mechanism/purpose/steps/formula coverage.
   - Add only generic fixes for repeated safe rejection patterns.
   - Re-run `--profile multi-doc-representative` after each change.
   - Tighten prompt/context only when trace data shows the prompt is larger than needed.
   - Consider chat-model warmup for demos or local production startup.

2. Improve trace UI summaries
   - Show compact labels for `evidence_path` and `answer_path` in the trace view.
   - Keep full JSON details expandable for debugging.

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
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --profile multi-doc-representative --warmup --output var\logs\latency_multi_doc_after_change_report.json
```

## Important Reminders

- Stop the web server before full local RAG evals if Qdrant path locking appears.
- Put generated reports in `var\logs`.
- Keep the system general-purpose for many unseen PDFs.
- Do not add hardcoded PDF-specific keywords.
