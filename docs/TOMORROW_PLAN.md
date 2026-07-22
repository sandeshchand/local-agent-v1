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
- Five-query latency improved from `16527.31 ms` average to `5170.94 ms` after evidence fast path, then to `2208.78 ms` after answer fast path.
- Warmed retrieval produced a best five-query sample of `199.51 ms` average and a latest repeated sample of `1694.8 ms` average because one harder answer still used normal LLM generation.
- The latest warmed five-query sample is `227.06 ms` average with `248.38 ms` p95.
- Full RAG regression passed with `9.48/10` average quality and all items above the configured `7/10` item gate.
- The latest changes are still uncommitted.

## First Task Tomorrow

Commit today's validated fast-path latency work before starting new behavior.

```powershell
git status --short
git add -A
git commit -m "perf: refine low-value fast-path filtering"
```

After that, push and merge only if the branch still looks clean.

## Recommended Feature Order

1. Broaden latency coverage across document families
   - Run warmed latency for representative Sora, Docker, ML, Python, and article-style questions.
   - Inspect `answer_path` and `answer_trace.fast_path.rejections` for the slowest traces in each family.
   - Add only generic fixes for repeated safe rejection patterns.
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
```

## Important Reminders

- Stop the web server before full local RAG evals if Qdrant path locking appears.
- Put generated reports in `var\logs`.
- Keep the system general-purpose for many unseen PDFs.
- Do not add hardcoded PDF-specific keywords.
