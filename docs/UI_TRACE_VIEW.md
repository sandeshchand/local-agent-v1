# UI Trace View

The web UI includes a trace inspector on the right side of the chat screen.

It helps debug answer quality without opening JSON reports manually.

## What It Shows

For each chat response, the trace view shows:

- query and trace id,
- plan mode,
- top-k setting,
- evidence count,
- tool result count,
- orchestration timeline,
- retrieved evidence preview,
- tool results,
- raw trace JSON.

Timeline steps can include:

- `memory`
- `plan`
- `retrieve`
- `guardrail`
- `tool_call`
- `verify`
- `answer_repair`
- `retrieval_retry_decision`

## How To Use

Start the web app:

```cmd
uvicorn app.web:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Ask a question. The assistant response includes a trace button. Click it to load the full trace in the right-side panel.

The Recent section also shows recent traces from SQLite.

## Important Fix

The web chat endpoint now returns the orchestrator trace id directly.

This matters because the orchestrator trace contains the full steps, tool results, and verification payload. The web route no longer creates a second thin trace without the orchestration details.

## Evidence Boundary

Trace evidence is for debugging. It does not change answer behavior.

PDF answers must still cite retrieved PDF chunks. Tool output, including weather output, is shown as tool context and not as PDF evidence.

## Verification

Run:

```cmd
venv\Scripts\python.exe -m py_compile app\web.py app\api_models.py storage\sqlite_store.py
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```

For a full local quality gate:

```cmd
venv\Scripts\python.exe scripts\run_regression.py
```
