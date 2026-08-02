# Tool Audit

Tool audit visibility summarizes guarded tool calls from saved traces.

It is read-only. It does not approve, deny, or execute tools. It only makes previous guardrail decisions easier to inspect.

## What It Shows

The API and UI show one audit row per `guardrail` trace step:

- trace id,
- session id,
- user query,
- tool name,
- tool source,
- tool category,
- guardrail status,
- approval requirement,
- request approval status,
- execution status,
- tool success,
- risk level,
- blocked status,
- guardrail reason,
- timestamp.

Supported statuses come from guardrails:

```text
allow
deny
needs_approval
```

## Tool Categories

The audit builder classifies tools generically from tool metadata and tool names:

```text
read_file
read_db
web_read
write_file
delete_file
mcp_read
local_read
```

These categories are for visibility first. They prepare the system for stronger future policies around write/delete tools.

## Risk Visibility

The audit also adds a generic risk label:

```text
low
medium
high
```

High risk is used for denied actions and write/delete-capable tool categories. Medium risk is used for approval-required or approval-pending actions. Low risk is used for normal read-only tool decisions.

The UI highlights:

- blocked actions,
- high-risk actions,
- write/delete categories,
- risk reason for each guarded tool call.

## API

Endpoint:

```text
GET /api/tools/audit?limit=50
```

Response shape:

```json
{
  "summary": {
    "total_count": 4,
    "allow_count": 2,
    "deny_count": 1,
    "needs_approval_count": 1,
    "approved_count": 1,
    "executed_count": 2,
    "blocked_count": 2,
    "high_risk_count": 2,
    "write_delete_count": 1
  },
  "items": []
}
```

The endpoint reads from SQLite traces through:

```text
src/local_agent/app/tool_audit.py
src/local_agent/storage/sqlite_store.py
```

## UI

The web workspace has an `Audit` tab.

It shows:

- summary tiles,
- recent guarded tool calls,
- status pills,
- category and source labels,
- whether the tool executed,
- whether the call was approved,
- an `Open trace` action for each audit item.

## Evidence Boundary

Tool audit is operational metadata. It is not document evidence and should never be used as a PDF citation source.

## Verification

Run:

```cmd
venv\Scripts\python.exe -m py_compile src\local_agent\app\tool_audit.py src\local_agent\app\web.py src\local_agent\app\api_models.py src\local_agent\storage\sqlite_store.py
venv\Scripts\python.exe scripts\smoke_tool_audit.py
node --check static\chat.js
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```
