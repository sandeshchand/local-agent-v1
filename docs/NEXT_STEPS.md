# Next Engineering Steps

This project is now in a good place for multi-document RAG: ingestion, routing, retrieval, answer generation, verification, repair, memory, and stronger orchestration are working.

The next work should improve reliability around tools, external integrations, user visibility, and repeatable evaluation.

## 1. Commit The Current Stable Point

Goal: save the current orchestration work before starting a new feature.

Why this matters:

- The orchestration layer now has a cleaner pipeline.
- Retrieval can retry once when the first answer has no citations or fails verification.
- Documentation is updated.
- Evaluation passed the quality gate.

Before committing, run:

```cmd
venv\Scripts\python.exe -m py_compile agent\orchestrator.py
venv\Scripts\python.exe scripts\smoke_memory.py
```

The full RAG benchmark was already run after the orchestration change. Run it again before major releases or before pushing a risky change:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --eval-file benchmarks\gold_qa\eval_multi_doc_rag.json --output eval\rag_quality_report.json --fail-under-average 8 --fail-under-item 7
```

## 2. Add Guardrails

Goal: make the agent safer before it executes tools, MCP actions, file operations, or external actions.

Status:

- Tool-call guardrails v1 is implemented.
- Request-scoped approval for approval-required tools is implemented.
- MCP-style tools now reuse the same guardrail shape.
- File-operation guardrails are still future work.

Implemented:

- A guardrail module that checks the planned action before execution.
- A simple policy result: `allow`, `deny`, or `needs_approval`.
- Trace logging for every guardrail decision.
- Clear user-facing messages when an action is denied.

Next guardrail work:

- Add file-operation categories before write/delete tools are introduced.
- Add path allowlists before a File MCP server can write or delete files.

Important rule:

Memory and tools can guide the agent, but PDF answers must still be grounded in retrieved document evidence and citations.

## 3. Improve MCP Integration

Goal: support external tools through a clean connector layer.

Status:

- A narrow read-only current weather web tool is implemented.
- A generic MCP adapter layer is implemented in `src/local_agent/app/mcp_adapter.py`.
- A read-only local File MCP connector is implemented in `src/local_agent/app/file_mcp.py`.
- A read-only SQLite inspection connector is implemented in `src/local_agent/app/sqlite_mcp.py`.
- Registered tools are visible through `GET /api/tools`.
- Registered tools are visible in the UI.
- The UI can approve approval-required tool calls for one request.
- File MCP roots are allowlisted through `FILE_MCP_ROOTS`.

What to implement:

- A concrete MCP client wrapper for the chosen transport.
- Optional browser smoke coverage for MCP tool answers in the UI.
- Stronger path policy before write/delete file tools.

Important rule:

MCP output should be treated as tool context, not as PDF evidence. If the user asks a document question, citations should still come from the indexed documents.

## 4. Improve UI Trace Visibility

Goal: make bad answers easier to debug from the app UI.

Status:

- UI trace inspector is implemented in the web app.
- The web chat endpoint now returns the full orchestrator trace id.
- Answer citations are shown in one compact source box.
- Users can store like/dislike feedback for each answer trace.

It shows:

- selected plan mode,
- routed documents,
- retrieval attempt count,
- retry reason,
- evidence chunks,
- verifier status,
- answer repair status,
- final citations,
- guardrail decisions,
- tool results.

This will help us quickly understand whether a bad answer came from routing, retrieval, evidence selection, answer generation, or verification.

## 5. Add A Regression Command

Goal: make quality checks repeatable before every commit.

Status:

- `scripts/run_regression.py` is implemented.

It runs:

- Python compile checks,
- memory smoke test,
- guardrails smoke test,
- File MCP and SQLite MCP smoke tests,
- weather tool smoke test,
- focused RAG eval,
- optional full RAG eval.

Standard command:

```cmd
venv\Scripts\python.exe scripts\run_regression.py
```

Full benchmark:

```cmd
venv\Scripts\python.exe scripts\run_regression.py --full --output eval\rag_quality_report.json
```

## 6. Expand Gold QA For New PDFs

Goal: keep the RAG system general-purpose as new documents arrive.

For every new PDF, add 3-5 gold QA items:

- definition question,
- feature/component question,
- how/why question,
- limitation or risk question,
- practical/application question.

This prevents us from optimizing only for the current small document set.
