# Authentication And Session Isolation

This document describes the v1 authentication, user namespace, and session-isolation layer.

## Current Scope

Authentication v1 protects API routes with one configured API token. It is intentionally small:

- local development remains open by default,
- `/api/*` routes require a token when auth is enabled,
- `/health`, `/`, and static assets remain public,
- chat, traces, memory, feedback, and tool-audit views use a request user/session namespace,
- PDF evidence is scoped to global documents plus the authenticated user's own ingested documents.

This is not full multi-user account management. It is a production-readiness step that adds a real API gate and prevents one authenticated user/session namespace from casually seeing another namespace's traces, feedback, and session memory.

## Enable Auth

Set these values in `.env`:

```env
AUTH_ENABLED=true
AUTH_TOKEN=replace-with-a-long-random-token
AUTH_ADMIN_USERS=alice,bob
```

If `AUTH_ENABLED=true` and `AUTH_TOKEN` is empty, the app refuses the API configuration.

`AUTH_ADMIN_USERS` is optional. If it is empty, every authenticated token user is treated as admin for backward-compatible single-token deployments. Once it is set, only listed user ids receive the `admin` role. Use `*` only for an explicit all-admin setup.

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

Set the user namespace with:

```text
X-Local-Agent-User: alice
```

When auth is enabled, the app stores runtime state under:

```text
<user_id>:<session_id>
```

For example, `X-Local-Agent-User: alice` and `X-Local-Agent-Session: default` becomes stored session `alice:default`.

When auth is disabled, the session defaults to `default`, but the session header may still be used for local testing.

Example:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/traces `
  -Headers @{
    Authorization = "Bearer $env:LOCAL_AGENT_TOKEN"
    "X-Local-Agent-User" = "alice"
    "X-Local-Agent-Session" = "demo"
  }
```

## Web UI Usage

The web UI has an `Access` panel in the left sidebar.

Use it to save:

- API token,
- user id,
- session id.

The browser stores these values in local storage and sends them with API calls. Clear the API token field and save again to remove the stored token.

## User And Session Isolation

When auth is enabled:

- `/api/chat` stores conversation turns and traces under the effective user/session id,
- `/api/traces` lists only the effective user/session traces,
- `/api/traces/{trace_id}` returns `404` for traces from another session,
- `/api/feedback` and `/api/feedback/summary` are filtered by session,
- `/api/tools/audit` is filtered by session,
- `/api/memory` uses the effective user/session id,
- deleting session memory from another session is blocked.
- trace-derived eval drafts are filtered by the owning trace session.
- document library, ingestion status, document routing, and retrieval are filtered to global plus current-user documents.

Two users can safely use the same visible session label. For example:

```text
alice/default -> alice:default
bob/default   -> bob:default
```

Global memory is still shared because it represents project-wide guidance.

## Admin Role

Admin role checks protect sensitive API actions.

Current admin-only API actions:

- ingest PDFs through `POST /api/ingest-path`,
- promote reviewed eval candidates into the gold QA file through `POST /api/eval-candidates/{candidate_id}/promote`.

Examples:

```env
AUTH_ADMIN_USERS=alice
```

With that config:

- `X-Local-Agent-User: alice` can ingest and promote eval candidates,
- `X-Local-Agent-User: bob` can still chat, read own traces, give feedback, and manage own session memory,
- `bob` receives `403` for admin-only actions.

CLI backup and restore commands are operator workflows. They are protected by machine/terminal access, not web API roles.

## What Is Still Shared

These are still shared in v1:

- Qdrant collection,
- gold QA files,
- underlying eval draft JSON files,
- global memory,
- local tools and tool registry.

Existing indexed documents default to global visibility. New authenticated web ingests are user-owned. See [docs/DOCUMENT_ISOLATION.md](DOCUMENT_ISOLATION.md).

For real multi-user production, add separate user accounts or an external identity provider, decide whether tenants need physically separate vector collections, add durable per-user eval storage, and replace header-based user namespaces with identity-provider claims. The `X-Local-Agent-User` header is a namespace input, not proof of identity by itself.

## Validation

Run:

```powershell
venv\Scripts\python.exe scripts\smoke_auth.py
venv\Scripts\python.exe scripts\smoke_document_isolation.py
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```
