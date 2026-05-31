# UI Trace View

The web UI includes a right-side workspace for trace inspection, recent runs, feedback review, and eval drafts.

It helps debug answer quality without opening JSON reports manually.

## What It Shows

The workspace uses tabs so the important panels do not stack below the fold:

- `Trace` shows the selected answer trace,
- `History` shows recent traces,
- `Feedback` shows feedback analytics and review actions,
- `Evals` shows feedback-derived eval drafts.

For each chat response, the trace tab shows:

- query and trace id,
- plan mode,
- top-k setting,
- evidence count,
- tool result count,
- orchestration timeline,
- retrieved evidence preview,
- tool results,
- raw trace JSON.

The answer card keeps the main action area visible:

- thumbs-up/thumbs-down feedback and the trace button are directly below the answer,
- all answer sources are shown in one collapsible source box,
- long file paths are shortened to the file name,
- the full source path remains available as hover text.

The right-side workspace includes a visible Tools tab:

- registered tools are loaded from `/api/tools`,
- local and MCP tools are shown together,
- the tool list can be searched,
- read-only tools and approval-required tools are visibly labeled.

The left sidebar also includes a scalable Library panel:

- the UI loads a small page of indexed documents instead of every PDF,
- the document count is shown above the list,
- title/path search is handled through the backend,
- `Load more` fetches the next page when the library is large.

If a tool action requires approval, the answer card shows an approval prompt. Clicking `Approve and run` repeats the same query with that tool approved for the current request only.

Each answer has feedback controls:

- the thumbs-up button stores positive feedback for the trace,
- the thumbs-down button stores negative feedback for the trace,
- changing the selection updates the same trace feedback row.

The `Feedback` workspace tab includes a feedback review section:

- summary tiles show total feedback, likes, dislikes, and dislike rate,
- `All` shows recent feedback,
- `Liked` shows positive feedback,
- `Disliked` shows negative feedback,
- selecting a feedback item opens the full trace.
- disliked items include a `Create eval` action that writes a draft candidate.
- disliked items can be tagged as wrong document, bad retrieval, weak answer, missing citation, tool issue, or other.

The `Evals` workspace tab supports:

- reviewing candidates created from disliked answers,
- editing expected answer and requirement fields,
- saving reviewed drafts,
- promoting reviewed drafts into `benchmarks/gold_qa/eval_multi_doc_rag.json`.
- running a targeted eval for a promoted draft and viewing the score, missing facts, routing, verifier, and answer.

Detailed feedback analytics notes:

```text
docs/FEEDBACK_ANALYTICS.md
```

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
uvicorn local_agent.app.web:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Ask a question. The assistant response includes feedback buttons and a trace button directly below the answer. Click the trace button to load the full trace in the right-side workspace.

The `History` tab shows recent traces from SQLite.

## Important Fix

The web chat endpoint now returns the orchestrator trace id directly.

This matters because the orchestrator trace contains the full steps, tool results, and verification payload. The web route no longer creates a second thin trace without the orchestration details.

## Evidence Boundary

Trace evidence is for debugging. It does not change answer behavior.

PDF answers must still cite retrieved PDF chunks. Tool output, including weather output, is shown as tool context and not as PDF evidence.

Feedback is also metadata. It does not change answer behavior during the same request. It gives us data for later evaluation and ranking improvements.

## Verification

Run:

```cmd
venv\Scripts\python.exe -m py_compile app\web.py app\api_models.py storage\sqlite_store.py
venv\Scripts\python.exe scripts\smoke_feedback_analytics.py
venv\Scripts\python.exe scripts\smoke_feedback_issue_tags.py
venv\Scripts\python.exe scripts\smoke_eval_candidates.py
venv\Scripts\python.exe scripts\smoke_eval_candidate_review.py
venv\Scripts\python.exe scripts\smoke_eval_candidate_run.py
venv\Scripts\python.exe scripts\smoke_tool_approval_ui.py
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```

For a full local quality gate:

```cmd
venv\Scripts\python.exe scripts\run_regression.py
```
