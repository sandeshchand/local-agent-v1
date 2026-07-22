# Next Engineering Steps

The project is now beyond the early prototype stage. Multi-document PDF RAG, routing, retrieval, answer generation, verification, repair, memory, guarded tools, MCP-style local connectors, UI traces, feedback, and regression checks are working.

The next work should focus on production hardening: keep answer quality high, measure latency, improve only the slowest stages, and grow evaluation coverage for more PDFs.

For the next focused session, see [docs/TOMORROW_PLAN.md](TOMORROW_PLAN.md).

## Current Stable State

Implemented:

- Multi-PDF ingestion with metadata-rich chunks.
- Document routing before chunk retrieval.
- Hybrid retrieval with dense search, BM25, fusion, reranking, and context expansion.
- Neighbor and parent context expansion for better evidence coverage.
- Evidence-grounded answer generation with citations.
- Answer verification, answer repair, and one retrieval retry path.
- Answer cleanup for raw chunk leakage, invalid citations, mojibake text, and repeated spans.
- Short-term and long-term memory.
- Memory multi-turn eval for project rules, preferences, task status, follow-up context, and sensitive-text redaction.
- Memory management API and UI tab for inspecting/deleting long-term memory.
- Tool-call guardrails with `allow`, `deny`, and `needs_approval`.
- Request-scoped approval for approval-required tools.
- Tool audit API and UI tab for guardrail/tool execution visibility.
- Read-only weather tool.
- MCP-style File and SQLite connectors.
- UI trace view, compact source box, feedback, eval drafts, document library, and tools panel.
- System status API and UI panel for SQLite, Qdrant, Ollama models, embeddings, and tools.
- Runtime backup and restore for local SQLite and Qdrant state.
- Local deployment guide for startup, config, health checks, logs, backup/restore, rollback, and Qdrant path ownership.
- Answer-generation fast path for high-confidence citation-backed extractive answers.
- Retrieval/model warmup for Qdrant, embeddings, and reranker startup cost.
- Fast-path observability through `evidence_trace`, `answer_trace`, `evidence_path`, and `answer_path`.
- Regression command with compile, smoke, tool, memory, config, empty-index, and answer-cleaning checks.

## 1. Reduce Remaining LLM Fallback Latency

Goal: reduce the remaining slow answers without weakening answer quality.

Evidence selection, answer generation, and retrieval/model warmup have already been optimized with safe high-confidence paths:

- average latency improved from `16527.31 ms` to `5170.94 ms`,
- answer fast path improved the latest 5-query average to `2208.78 ms`,
- retrieval warmup produced a best warmed 5-query average of `199.51 ms`,
- the latest repeated warmed sample had `240.19 ms` p50 and `1694.8 ms` average because one question correctly fell back to normal LLM answer generation,
- evidence selection dropped to about `1.75ms` to `2.45ms`,
- fast-path answer generation is about `6ms` to `20ms` on the sampled high-confidence questions,
- full RAG quality passed at `9.51/10` with `45/45` items at `>= 8/10`.

Fast-path observability is now available in retrieval trace steps:

- `evidence_path`
- `answer_path`
- `evidence_trace`
- `answer_trace`

Use these fields to inspect slow answers before changing behavior.

Recommended order:

1. Run a warmed latency benchmark.
2. Inspect `answer_path` for the slowest query.
3. If `answer_path=llm_generation`, inspect `answer_trace.fast_path.rejections`.
4. Add only generic fixes for repeated safe rejection patterns.
5. Tighten prompt/context only where traces show excess context.
6. Consider chat-model warmup for demos where first LLM answer latency matters.
7. Keep citations, verification, and repair intact.

Do not remove verification or answer repair as the first performance optimization. They protect answer quality.

After each optimization, run:

```cmd
venv\Scripts\python.exe scripts\run_regression.py
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --limit 5 --warmup --output var\logs\latency_after_change_report.json
```

## 2. Optimize One Slow Stage

If latency remains high after answer-path observability, optimize one slow stage at a time:

- if normal LLM answer generation is slow, inspect prompt size and context size,
- if reranking is slow after warmup, tune `RERANK_CANDIDATES`,
- if routing is slow, cache document routing results,
- if embedding is slow, cache repeated query embeddings,
- if retrieval is slow for larger data, consider Qdrant server mode instead of local path mode.

Keep these constraints:

- keep citations, verification, and repair intact,
- re-run full RAG quality after any retrieval/warmup shortcut.

## 3. Expand Gold QA

Goal: keep the system general-purpose as more documents arrive.

For every new PDF, add 3 to 5 gold QA items:

- definition question,
- feature/component question,
- how/why question,
- limitation or risk question,
- practical/application question.

This prevents the system from being tuned only for Sora, Docker, or the current Medium/article PDFs.

## 4. Add Scheduled Backup Policy

Goal: protect runtime state outside the local repo.

Define:

- backup storage location,
- backup frequency,
- retention period,
- restore-drill schedule,
- who owns rollback decisions.

Local backup/restore already works; this step turns it into an operating policy.

## 5. Future Guardrail Work

Do this before adding write/delete tools.

Next guardrail tasks:

- add file-operation categories,
- add explicit path allowlists for writable tools,
- extend audit filters if the trace volume grows,
- keep approval request-scoped unless there is a real user/session permission model.

Important rule: memory and tools can guide the agent, but PDF answers must still come from retrieved PDF evidence and citations.

## 6. Future MCP Work

Current MCP-style tools are local read-only connectors. They are useful and safe for the current app.

Later MCP work:

- add a concrete MCP transport client only when an external MCP server is needed,
- add browser/UI smoke coverage for MCP tool answers,
- keep arbitrary SQL disabled,
- keep file write/delete disabled until stronger guardrails exist.

MCP output is tool context, not PDF evidence.
