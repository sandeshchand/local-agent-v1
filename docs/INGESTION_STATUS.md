# Ingestion Status

Ingestion status records make batch PDF indexing observable.

The system now stores the latest ingestion attempt for each source path in SQLite. This helps answer operational questions such as:

- Which PDFs were indexed?
- Which PDFs were skipped because they were already current?
- Which PDFs failed?
- Which parser/chunking/embedding settings produced the current index?

## Stored Fields

Each status record includes:

```text
source_path
doc_id
title
status
parser_version
chunking_version
embedding_model
chunk_size
chunk_overlap
checksum
page_count
chunk_count
started_at
completed_at
error
```

Status values:

- `running`: ingestion started and has not completed yet,
- `indexed`: PDF was parsed, chunked, embedded, and stored,
- `skipped`: PDF was already current and did not need rebuilding,
- `failed`: ingestion failed and the error was recorded.

## CLI

Show recent ingestion attempts:

```powershell
local-agent ingest-status
```

Show only failures:

```powershell
local-agent ingest-status --status failed
```

Limit rows:

```powershell
local-agent ingest-status --limit 50
```

## API

Use:

```text
GET /api/ingestion/status
GET /api/ingestion/status?status=failed&limit=50
```

The response includes summary counts and recent records.

## UI

Open the web UI and use the `Ingest` workspace tab.

The tab shows:

- total/indexed/skipped/failed/running counts,
- status filter,
- recent ingestion attempts,
- parser/chunking/embedding settings,
- failure error text.

## Operational Notes

Default ingest is incremental:

```powershell
local-agent ingest --path data\raw\documents
```

Use `--force` only when intentionally rebuilding:

```powershell
local-agent ingest --path data\raw\documents --force
```

After parser or chunking behavior changes, bump `PARSER_VERSION` or `CHUNKING_VERSION` in:

```text
src/local_agent/ingestion/metadata.py
```

That makes normal ingestion rebuild affected PDFs instead of silently reusing old chunks.
