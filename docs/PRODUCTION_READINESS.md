# Production Readiness

This document tracks what must be true before the local agentic RAG system should be treated as production-ready.

The target is not only "the app runs." The target is a measurable, observable, safe, recoverable RAG product.

## Current Position

The project has strong local foundations:

- multi-PDF ingestion,
- hybrid retrieval,
- document routing,
- grounded answer generation,
- verification and answer repair,
- memory,
- guarded tool execution,
- MCP-style read-only local connectors,
- feedback capture,
- repeatable evaluation,
- trace visibility,
- system-status visibility for SQLite, Qdrant, Ollama models, embeddings, and tools.
- local backup and restore tooling for SQLite and Qdrant runtime state.

The project is ready for serious local iteration and controlled demos. It still needs deployment, security, monitoring, and broader benchmark coverage before production use.

## Production Layers

```text
Data ingestion
-> chunking
-> indexing and storage
-> document routing
-> retrieval
-> evidence selection
-> answer generation
-> verification and repair
-> orchestration
-> guardrails and tools
-> memory
-> UI/API
-> evaluation
-> observability
-> operations
```

## Readiness Checklist

### Data And Indexing

- Define supported document formats and maximum file sizes.
- Add ingestion status tracking for each document.
- Record parser version and chunking version for each indexed document.
- Add safe reingestion workflow for changed PDFs.
- Keep the local backup and restore process tested for `var/sqlite/app.db` and `var/qdrant/`.

### Repository Structure

- Move production code to a `src/` layout.
- Keep automated tests in `tests/`.
- Keep gold QA benchmark files outside the test package, for example `benchmarks/gold_qa/`.
- Keep local runtime state under `var/`.
- Prefer console entry points such as `local-agent` over file-path commands such as `python -m local_agent.app.main`.

### Retrieval Quality

- Keep gold QA in `benchmarks/gold_qa/eval_multi_doc_rag.json`.
- Add 3 to 5 gold QA items per important new PDF.
- Track document-routing failures separately from answer-generation failures.
- Keep regression thresholds visible and enforced.
- Add eval coverage for large unseen document batches.

### Answer Quality

- Keep verifier and answer repair generic.
- Do not add document-specific hardcoded answer logic.
- Track citation correctness, wrong-document answers, missing facts, and unsupported drift.
- Use user dislikes to create eval candidates, not automatic hidden optimization.

### Safety And Guardrails

- Keep all tool execution behind guardrails.
- Default unknown or missing tools to `deny`.
- Require approval for tools that can perform broad external or risky actions.
- Keep file tools read-only until path policy and audit controls are stronger.
- Never treat tool output as PDF citation evidence.

### MCP And Tools

- Current MCP layer is MCP-style and local.
- Before external MCP servers, add explicit server configuration.
- Validate tool schemas before execution.
- Add audit logging for approved tool calls.
- Use read-only defaults for file, database, and web tools.

### Memory

- Keep memory as guidance, not evidence.
- Continue filtering sensitive text before storing memory.
- Add memory-specific multi-turn eval tests.
- Add UI controls to inspect and delete long-term memory.
- Consider semantic memory retrieval only after lexical behavior is stable.

### UI And Product Experience

- Keep answer, sources, trace, tools, and feedback visible without crowding.
- Make failure states clear and actionable.
- Keep eval drafts and feedback review understandable to non-engineers.
- Keep admin-style views for evaluation reports and system health understandable and actionable.

### Security And Privacy

- Add authentication before multi-user deployment.
- Add user/session isolation.
- Move production secrets to a proper secret manager.
- Define data retention rules for traces, feedback, memory, and uploaded PDFs.
- Review logs to ensure they do not expose sensitive content unnecessarily.

### Deployment And Operations

- Add a deployment plan: local service, container, or managed host.
- Keep health checks for web, SQLite, Qdrant, Ollama, and model availability visible in the UI/API.
- Add monitoring for latency, failed retrievals, failed tool calls, and eval regressions.
- Add process control so only one local Qdrant path owner runs at a time.
- Keep backup and restore instructions current, and add rollback instructions for deployed environments.

## Minimum Production Gate

Before calling this production-ready, the project should pass:

```powershell
venv\Scripts\python.exe scripts\run_regression.py
venv\Scripts\python.exe scripts\eval_rag_quality.py --eval-file benchmarks\gold_qa\eval_multi_doc_rag.json --output eval\rag_quality_report.json --fail-under-average 8 --fail-under-item 7
```

It should also have:

- documented deployment steps,
- documented backup and restore,
- authentication decision,
- data retention decision,
- at least one evaluation report for the target production document set,
- no known critical wrong-document retrieval issues.

## Near-Term Priorities

1. Add memory-specific multi-turn eval tests.
2. Add a production deployment document.
3. Add broader gold QA for new daily PDFs.
4. Add stronger tool approval audit views.
5. Add UI controls to inspect and delete long-term memory.
6. Add scheduled/off-machine backup policy for deployed environments.

Completed from this list:

- Health-check and system-status UI/API endpoints.
- Local SQLite and Qdrant backup/restore script, smoke test, and documentation.
