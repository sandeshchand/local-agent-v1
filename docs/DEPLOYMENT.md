# Deployment Guide

This guide describes the current deployment shape for the local agentic RAG system.

The current supported deployment is a single-machine, local-first deployment using:

- one FastAPI web process,
- local SQLite,
- local Qdrant path storage,
- local Ollama chat and embedding models,
- read-only local tools by default.

This is suitable for controlled demos, local team development, and single-user operation. For production-like local use, enable API token auth. Before true multi-user production, add full user accounts, per-user document isolation, external secret management, monitoring, and a stronger backup policy.

## 1. Prepare The Host

Install:

- Python supported by the project,
- Git,
- Ollama,
- enough disk space for PDFs, SQLite, Qdrant, model files, logs, and backups.

Create the virtual environment:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

Install the app:

```powershell
pip install -e .
```

Optional OCR support:

```powershell
pip install -e .[ocr]
```

Pull local models:

```powershell
ollama pull qwen2.5:7b-instruct
ollama pull nomic-embed-text
```

## 2. Configure `.env`

Start from the example:

```powershell
copy .env.example .env
```

Recommended local deployment defaults:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
CHAT_MODEL=qwen2.5:7b-instruct
EMBED_MODEL=nomic-embed-text
QDRANT_PATH=./var/qdrant
SQLITE_PATH=./var/sqlite/app.db
TOP_K=5
CHUNK_SIZE=800
CHUNK_OVERLAP=120
DEBUG=false
USE_RERANKER=true
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RERANK_CANDIDATES=8
WARM_RETRIEVAL_ON_STARTUP=false
FILE_MCP_ENABLED=true
FILE_MCP_ROOTS=data,docs,benchmarks,tests,README.md,pyproject.toml
AUTH_ENABLED=false
AUTH_TOKEN=
```

Keep `.env` out of Git. Use `.env.example` for safe placeholders.

Set `WARM_RETRIEVAL_ON_STARTUP=true` for demos or local production when first-question latency matters. This warms the Qdrant collection check, embedding model, and reranker during startup. Keep it `false` for the fastest development startup.

For production-like local use, set `AUTH_ENABLED=true` and provide a long random `AUTH_TOKEN`. Save that token and a session id in the web UI `Access` panel. See [AUTHENTICATION.md](AUTHENTICATION.md).

For deployed environments, do not store real secrets in the repo. Move secrets to the host secret manager or deployment platform when the app becomes multi-user.

## 3. Ingest Documents

Place PDFs under:

```text
data/raw/documents/
```

Run:

```powershell
local-agent ingest --path data\raw\documents
```

Confirm documents:

```powershell
local-agent list-docs
```

For large ingest or parser/chunking changes, create a backup first.

## 4. Start The Web App

Use the helper script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_web.ps1
```

The script:

- stops existing `local_agent.app.web:app` or `app.web:app` uvicorn processes,
- starts from `venv\Scripts\python.exe`,
- waits for `/health`,
- prints the process that owns the port,
- writes logs to `var/logs/`.

Default URL:

```text
http://127.0.0.1:8000
```

Custom host/port:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_web.ps1 -HostAddress 127.0.0.1 -Port 8001
```

## 5. Health Checks

Basic web check:

```text
GET /health
```

Detailed runtime check:

```text
GET /api/system/status
GET /api/system/status?check_models=false
```

The detailed status checks:

- SQLite,
- Qdrant collection,
- Ollama chat model,
- Ollama embedding model,
- tool registry.

You can also inspect the `System` tab in the web UI.

## 6. Logs

Web startup logs:

```text
var/logs/web.out.log
var/logs/web.err.log
```

Generated local reports:

```text
var/logs/rag_quality_report.json
var/logs/memory_quality_report.json
var/logs/latency_benchmark_report.json
```

Do not commit `var/logs/`.

## 7. One-Server Rule For Local Qdrant

Local Qdrant path mode allows one active owner of the Qdrant folder.

Do not run these at the same time against the same `QDRANT_PATH`:

- web server,
- full RAG eval,
- ingestion,
- another Python shell that bootstraps the app.

If you see:

```text
Storage folder ... is already accessed by another instance of Qdrant client.
```

stop old app/eval processes and rerun the command.

For concurrent production access, move from local Qdrant path mode to Qdrant server mode in a future deployment phase.

## 8. Backup

Back up before large ingest, parser changes, chunking changes, index reset, or deployment upgrades:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py --env-file .env backup
```

Backups are written under:

```text
var/backups/local_agent_backup_YYYYMMDD_HHMMSS/
```

For real production, copy backups to another disk or managed storage. Local backups alone are not enough.

Detailed backup notes:

```text
docs/BACKUP_RESTORE.md
```

## 9. Restore

Stop the web server first.

Inspect the backup:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py inspect --backup-path var\backups\local_agent_backup_YYYYMMDD_HHMMSS
```

Restore:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py --env-file .env restore --backup-path var\backups\local_agent_backup_YYYYMMDD_HHMMSS --force
```

The restore command moves existing runtime files aside before copying the backup.

After restore:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_web.ps1
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```

For important production datasets, also run:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --full --output var\logs\rag_quality_report.json
```

## 10. Rollback

Recommended rollback procedure:

1. Stop the web server.
2. Check out the last known good Git commit.
3. Restore the matching runtime backup.
4. Start the web server.
5. Check `/health` and `/api/system/status`.
6. Run `scripts\run_regression.py --skip-rag`.
7. Run a focused or full RAG eval if retrieval behavior changed.

Keep a note of:

- Git commit SHA,
- `.env` used,
- backup path,
- ingestion/chunking version or date,
- eval report path.

## 11. Deployment Quality Gate

Before a release or demo:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
venv\Scripts\python.exe scripts\run_regression.py --full --output var\logs\rag_quality_report.json
venv\Scripts\python.exe scripts\benchmark_latency.py --limit 5 --output var\logs\latency_benchmark_report.json
```

Expected quality gate:

- average RAG score at least `8/10`,
- important individual items at least `7/10`,
- no known critical wrong-document failures,
- health status is `ok` or an understood `degraded`,
- backup exists before risky deployment or reingest.

## 12. Not Production-Ready Yet

Before real multi-user production, add:

- authentication,
- per-user/session isolation,
- deployment secret management,
- scheduled off-machine backups,
- monitoring and alerting,
- container or service manager configuration,
- explicit data retention policy,
- stronger authorization for any future write/delete tools.
