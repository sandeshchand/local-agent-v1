# Memory UI And API

The Memory workspace tab lets users inspect and delete long-term memory items from the web UI.

Memory is project/user guidance only. It is not PDF evidence and must not be used as a citation source.

## What It Shows

The Memory tab shows durable records from the SQLite `memory_items` table:

- memory kind, such as `project_decision` or `user_preference`,
- scope, either `global` or `session`,
- source, either `manual` or `auto`,
- importance and access count,
- updated time,
- memory content.

The tab includes:

- a session id filter,
- a `Global` checkbox to include or exclude global memories,
- a refresh button,
- a delete button for stale or wrong memory items.

## API Endpoints

List memory items:

```text
GET /api/memory?session_id=default&include_global=true&limit=50
```

Delete one memory item:

```text
DELETE /api/memory/{memory_id}
```

The list endpoint is read-only. The delete endpoint removes one row from `memory_items`; it does not delete traces, chat history, PDFs, chunks, or evaluation data.

## Design Boundaries

The Memory UI intentionally manages long-term memory only.

Short-term conversation history remains part of the active session context and is not listed in this panel. Short-term turns are already redacted before storage when sensitive-looking values are detected.

Long-term memory can influence style, preferences, project rules, and workflow continuity. It cannot replace retrieval evidence for document answers.

## Verification

Run:

```cmd
venv\Scripts\python.exe -m py_compile src\local_agent\app\web.py src\local_agent\app\api_models.py src\local_agent\storage\sqlite_store.py
venv\Scripts\python.exe scripts\smoke_memory_api.py
node --check static\chat.js
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```
