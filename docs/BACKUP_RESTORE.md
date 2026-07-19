# Backup And Restore

This document explains how to back up and restore local runtime state.

Runtime state is not committed to Git. It normally lives under:

```text
var/sqlite/app.db
var/qdrant/
var/logs/
```

Only SQLite and Qdrant are part of the backup. Logs are runtime diagnostics and can be archived separately if needed.

## What Gets Backed Up

The backup command stores:

- SQLite app database: documents, chunks, traces, feedback, memory, and metadata.
- Qdrant local vector store directory.
- `metadata.json`: source paths, artifact sizes, timestamp, and backup format version.

The Qdrant `.lock` file is intentionally excluded. It is a runtime lock file, not durable data.
The backup metadata records whether the lock file existed at backup time, which is a useful signal that the web server may still have been running.

## Before Backup

For the safest backup, stop the web server first:

```powershell
Ctrl+C
```

or close the terminal running:

```powershell
uvicorn local_agent.app.web:app
```

This matters because local Qdrant path mode should have one owner at a time.

## Create A Backup

Use the same `.env` that your app uses:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py --env-file .env backup
```

By default, backups are written under:

```text
var/backups/local_agent_backup_YYYYMMDD_HHMMSS/
```

Use a custom backup root:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py --env-file .env backup --backup-root D:\local-agent-backups
```

Use an exact output directory:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py --env-file .env backup --output-dir D:\local-agent-backups\before_reingest
```

The exact output directory must be empty if it already exists.

## Inspect A Backup

```powershell
venv\Scripts\python.exe scripts\runtime_state.py inspect --backup-path var\backups\local_agent_backup_YYYYMMDD_HHMMSS
```

Check:

- `artifacts.sqlite.exists`
- `artifacts.qdrant.exists`
- source paths
- file counts and sizes

## Restore A Backup

Stop the web server before restore.

Restore requires `--force` if current runtime files already exist:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py --env-file .env restore --backup-path var\backups\local_agent_backup_YYYYMMDD_HHMMSS --force
```

When `--force` is used, existing runtime files are not deleted directly. They are moved aside first:

```text
var/sqlite/app.db.pre_restore_YYYYMMDD_HHMMSS
var/qdrant.pre_restore_YYYYMMDD_HHMMSS/
```

Then the backup is copied into the configured runtime paths.

Restore preflights target conflicts before copying data. If `--force` is missing and a target already exists, the command stops before changing either SQLite or Qdrant.

## After Restore

Start the web app:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_web.ps1
```

Check:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/api/system/status
```

Then run:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```

For important production data, also run a focused or full RAG quality eval.

## Recommended Timing

Create a backup before:

- reingesting many PDFs,
- changing parser or chunking logic,
- changing storage paths,
- deleting or resetting local databases,
- merging large retrieval/indexing changes.

## Safety Rules

- Do not commit files under `var/backups/`.
- Do not restore while another app process owns local Qdrant.
- Keep backup directories outside the repo for long-term storage.
- For production deployment, copy backups to a separate disk or managed storage.
