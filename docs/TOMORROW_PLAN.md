# Tomorrow Plan

Use this note to restart the next development session without losing the thread.

## Current State

The latest work moved the project closer to production readiness and improved RAG latency without weakening answer quality.

- Added local deployment documentation in `docs/DEPLOYMENT.md`.
- Added a high-confidence fast path in `EvidenceJudge`.
- Evidence selection now takes around 2ms on the sampled Sora queries.
- Added a high-confidence answer-generation fast path in `AnswerService`.
- Five-query latency improved from `16527.31 ms` average to `5170.94 ms` after evidence fast path, then to `2208.78 ms` after answer fast path.
- Full RAG regression passed with `9.39/10` average quality and no item below the configured `7/10` item gate.
- The latest changes are still uncommitted.

## First Task Tomorrow

Commit today's validated work before starting new behavior.

```powershell
git status --short
git add -A
git commit -m "perf: add high-confidence answer fast path"
```

After that, push and merge only if the branch still looks clean.

## Recommended Feature Order

1. Inspect first-query retrieval/model warmup
   - `sora_what_is` still shows a slower retrieval stage than later queries.
   - Check whether model loading, embedding startup, reranker startup, or Qdrant warmup is causing the first-query delay.
   - Prefer warmup/caching fixes over query-specific logic.

2. Broaden gold QA for new PDFs
   - Add more questions from unseen PDFs, daily medium-style articles, arXiv papers, and technical blog PDFs.
   - Keep every benchmark generic; do not add document-specific hardcoded keywords.

3. Continue production readiness
   - Define scheduled/off-machine backup policy.
   - Decide authentication and user-isolation plan.
   - Keep local backup/restore as the current base.

4. MCP and guardrails next step
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
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --limit 5 --output var\logs\latency_after_change_report.json
```

## Important Reminders

- Stop the web server before full local RAG evals if Qdrant path locking appears.
- Put generated reports in `var\logs`.
- Keep the system general-purpose for many unseen PDFs.
- Do not add hardcoded PDF-specific keywords.
