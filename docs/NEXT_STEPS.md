# Next Engineering Steps

The project is now beyond the early prototype stage. Multi-document PDF RAG, routing, retrieval, answer generation, verification, repair, memory, guarded tools, MCP-style local connectors, UI traces, feedback, and regression checks are working.

The next work should focus on production hardening: keep answer quality high, measure latency, improve only the slowest stages, and grow evaluation coverage for more PDFs.

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
- Tool-call guardrails with `allow`, `deny`, and `needs_approval`.
- Request-scoped approval for approval-required tools.
- Read-only weather tool.
- MCP-style File and SQLite connectors.
- UI trace view, compact source box, feedback, eval drafts, document library, and tools panel.
- System status API and UI panel for SQLite, Qdrant, Ollama models, embeddings, and tools.
- Runtime backup and restore for local SQLite and Qdrant state.
- Regression command with compile, smoke, tool, memory, config, empty-index, and answer-cleaning checks.

## 1. Run Full RAG Regression

Goal: confirm the current production-hardening changes did not reduce retrieval quality.

Run:

```cmd
venv\Scripts\python.exe scripts\run_regression.py --full --output eval\rag_quality_report.json
```

Pass rules:

- average score should stay above `8/10`,
- important individual items should stay above `7/10`,
- failed items should be inspected in the UI trace before changing retrieval logic.

If the full run passes, commit and push the current branch before starting another behavior change.

## 2. Add Memory-Specific Multi-Turn Evals

Goal: verify memory improves follow-up behavior without becoming unsupported PDF evidence.

Add small eval cases for:

- user preference remembered across turns,
- follow-up question using short-term context,
- PDF answer that must ignore unrelated memory,
- memory redaction or sensitive-text filtering behavior.

Keep memory evals separate from gold PDF QA because they test orchestration behavior, not document evidence.

## 3. Measure Performance Baseline

Goal: measure latency before optimizing anything.

Run:

```cmd
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --limit 5 --output eval\latency_baseline_report.json
```

Then inspect:

- slowest query,
- total latency,
- document routing time,
- retrieval search time,
- reranking time,
- evidence selection time,
- answer generation time.

Only optimize the slowest confirmed stage.

## 4. Optimize One Slow Stage

Recommended order:

1. If reranking is slow, tune `RERANK_CANDIDATES`.
2. If answer generation is slow, reduce context size or prompt size.
3. If routing is slow, cache document routing results.
4. If embedding is slow, cache repeated query embeddings.
5. If retrieval is slow for larger data, consider Qdrant server mode instead of local path mode.

Do not remove verification or answer repair as the first performance optimization. They protect answer quality.

After each optimization, run:

```cmd
venv\Scripts\python.exe scripts\run_regression.py
venv\Scripts\python.exe scripts\benchmark_latency.py --env-file .env --limit 5 --output eval\latency_after_change_report.json
```

## 5. Expand Gold QA

Goal: keep the system general-purpose as more documents arrive.

For every new PDF, add 3 to 5 gold QA items:

- definition question,
- feature/component question,
- how/why question,
- limitation or risk question,
- practical/application question.

This prevents the system from being tuned only for Sora, Docker, or the current Medium/article PDFs.

## 6. Future Guardrail Work

Do this before adding write/delete tools.

Next guardrail tasks:

- add file-operation categories,
- add explicit path allowlists for writable tools,
- add audit views for approved tool executions,
- keep approval request-scoped unless there is a real user/session permission model.

Important rule: memory and tools can guide the agent, but PDF answers must still come from retrieved PDF evidence and citations.

## 7. Future MCP Work

Current MCP-style tools are local read-only connectors. They are useful and safe for the current app.

Later MCP work:

- add a concrete MCP transport client only when an external MCP server is needed,
- add browser/UI smoke coverage for MCP tool answers,
- keep arbitrary SQL disabled,
- keep file write/delete disabled until stronger guardrails exist.

MCP output is tool context, not PDF evidence.
