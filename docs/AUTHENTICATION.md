# Authentication And Session Isolation

This document describes the v1 authentication and session-isolation layer.

## Current Scope

Authentication v1 protects API routes with one configured API token. It is intentionally small:

- local development remains open by default,
- `/api/*` routes require a token when auth is enabled,
- `/health`, `/`, and static assets remain public,
- chat, traces, memory, feedback, and tool-audit views use a request session id,
- PDF evidence and indexed documents are still shared across sessions.

This is not full multi-user account management. It is a production-readiness step that adds a real API gate and prevents one authenticated session from casually seeing another session's traces, feedback, and session memory.

## Enable Auth

Set these values in `.env`:

```env
AUTH_ENABLED=true
AUTH_TOKEN=replace-with-a-long-random-token
```

If `AUTH_ENABLED=true` and `AUTH_TOKEN` is empty, the app refuses the API configuration.

Generate a token with PowerShell:

```powershell
[Convert]::ToHexString((1..32 | ForEach-Object { Get-Random -Minimum 0 -Maximum 256 }))
```

## API Usage

Send the token with either header:

```text
Authorization: Bearer <token>
```

or:

```text
X-Local-Agent-Token: <token>
```

Set the session namespace with:

```text
X-Local-Agent-Session: team-a
```

When auth is disabled, the session defaults to `default`, but the session header may still be used for local testing.

Example:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/traces `
  -Headers @{
    Authorization = "Bearer $env:LOCAL_AGENT_TOKEN"
    "X-Local-Agent-Session" = "demo"
  }
```

## Web UI Usage

The web UI has an `Access` panel in the left sidebar.

Use it to save:

- API token,
- session id.

The browser stores these values in local storage and sends them with API calls. Clear the API token field and save again to remove the stored token.

## Session Isolation

When auth is enabled:

- `/api/chat` stores conversation turns and traces under the request session id,
- `/api/traces` lists only the request session's traces,
- `/api/traces/{trace_id}` returns `404` for traces from another session,
- `/api/feedback` and `/api/feedback/summary` are filtered by session,
- `/api/tools/audit` is filtered by session,
- `/api/memory` uses the authenticated session id,
- deleting session memory from another session is blocked.

Global memory is still shared because it represents project-wide guidance.

## What Is Still Shared

These are still shared in v1:

- indexed documents,
- document chunks,
- Qdrant collection,
- gold QA files,
- eval draft files,
- global memory,
- local tools and tool registry.

For real multi-user production, add separate user accounts, user-owned document collections, per-user feedback/eval stores, and admin roles.

## Validation

Run:

```powershell
venv\Scripts\python.exe scripts\smoke_auth.py
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```
