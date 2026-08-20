# Document Isolation

Document isolation protects indexed PDF content when API authentication is enabled.

## What V1 Does

- Existing documents default to `owner_id=global` and `visibility=global`.
- New web ingests under `AUTH_ENABLED=true` are stored as `owner_id=<current user>` and `visibility=user`.
- Document library and ingestion-status APIs show only global documents plus the current user's documents.
- Chat retrieval receives an explicit list of accessible document IDs.
- Document routing builds its scoped routing corpus from only those accessible document IDs.
- Hybrid retrieval intersects routed candidates with the accessible document IDs.
- Retrieval retry can broaden from routed documents to all accessible documents, but not to another user's private documents.
- The `list_documents` tool is scoped inside the orchestrator when the request carries an authenticated document scope.

## What Stays Global

When auth is disabled, CLI and local development workflows continue to see every indexed document. This keeps local regression, admin debugging, and one-user development simple.

Older indexes remain usable because SQLite migrations add:

```text
documents.owner_id DEFAULT 'global'
documents.visibility DEFAULT 'global'
document_ingestion_status.owner_id DEFAULT 'global'
document_ingestion_status.visibility DEFAULT 'global'
```

Qdrant chunk payloads for newly indexed documents also include `owner_id` and `visibility`. V1 still scopes retrieval by document IDs from SQLite, so old Qdrant payloads continue to work.

## Query Flow

Authenticated chat request:

```text
request user
-> SQLite accessible_document_ids(user)
-> document router receives accessible_doc_ids
-> router ranks only accessible documents
-> retrieval searches only routed accessible docs
-> retry broadens only to all accessible docs
-> answer cites only accessible chunks
```

## Same Path Reingestion

The local SQLite schema still has one row per `source_path`. If a PDF path is already indexed:

- global documents remain global when reingested by a user,
- the original owner is preserved for already user-owned documents,
- another user cannot overwrite a private document at the same path.

This is a safe v1 for local production-style use. A future multi-tenant deployment can replace path uniqueness with `(owner_id, source_path)` or a file-upload object ID.

## Regression

Document isolation is covered by:

```powershell
venv\Scripts\python.exe scripts\smoke_document_isolation.py
```

The smoke verifies:

- SQLite document filters,
- document router scoping,
- retrieval scoping,
- scoped `list_documents` tool output.
