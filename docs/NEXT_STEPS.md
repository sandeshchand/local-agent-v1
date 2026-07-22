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
- Regression command with compile, smoke, tool, memory, config, empty-index, and answer-cleaning checks.

## 1. Optimize Answer Generation Latency

Goal: reduce the new largest latency stage without weakening answer quality.

Evidence selection has already been optimized with a safe high-confidence fast path:

- average latency improved from `16527.31 ms` to `5170.94 ms`,
- p95 latency improved from `26323.34 ms` to `8643.61 ms`,
- evidence selection dropped to about `1.75ms` to `2.45ms`,
- full RAG quality passed at `9.47/10`.

Next change should inspect answer-generation prompts and context size. Good candidates:

- skip LLM answer generation when a deterministic extractive answer is already complete,
- reduce prompt context for simple definition/list questions,
- keep citations and verifier intact,
- re-run full RAG quality after any answer-generation shortcut.

## 2. Optimize One Slow Stage

Recommended order after answer generation:

1. If first-query retrieval remains slow, inspect reranker/model warmup.
2. If reranking is slow after warmup, tune `RERANK_CANDIDATES`.
3. If routing is slow, cache document routing results.
4. If embedding is slow, cache repeated query embeddings.
5. If retrieval is slow for larger data, consider Qdrant server mode instead of local path mode.

Do not remove verification or answer repair as the first performance optimization. They protect answer quality.

After each optimization, run:

```cmd
venv\Scripts\python.exe scripts\run_regression.py
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --limit 5 --output var\logs\latency_after_change_report.json
```

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
