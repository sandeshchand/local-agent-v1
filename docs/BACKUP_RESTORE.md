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

## List Backups

List backups under the default backup root:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py list-backups
```

List backups under a custom backup root:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py list-backups --backup-root D:\local-agent-backups
```

The command returns JSON summaries sorted newest first. It includes the backup path, creation time, SQLite/Qdrant artifact presence, artifact sizes, and source runtime paths.

## Prune Old Backups

Prune is dry-run by default. This shows what would be deleted while keeping the newest `7` valid backups:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py prune-backups --keep 7
```

Actually delete old backups only after reviewing the dry-run output:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py prune-backups --keep 7 --apply
```

Use a custom backup root:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py prune-backups --backup-root D:\local-agent-backups --keep 14 --apply
```

Prune only deletes valid backup directories directly under the selected backup root. Directories without `metadata.json` are ignored by listing and are not prune candidates.

## Scheduled Backup Job

Use `scheduled-backup` when an operating-system scheduler should run the whole backup workflow:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py --env-file .env scheduled-backup --backup-root D:\local-agent-backups --off-machine-root E:\local-agent-off-machine-backups --apply-prune
```

The command does four things:

- creates a normal runtime backup,
- optionally copies that backup to `--off-machine-root`,
- prunes local and off-machine backup roots by retention count,
- appends one JSON line to `var/logs/scheduled_backup.jsonl`.

Pruning is dry-run unless `--apply-prune` is included. Defaults:

```text
--local-keep 14
--off-machine-keep 28
--job-log var/logs/scheduled_backup.jsonl
```

Use a custom log path:

```powershell
venv\Scripts\python.exe scripts\runtime_state.py --env-file .env scheduled-backup --backup-root D:\local-agent-backups --off-machine-root E:\local-agent-off-machine-backups --job-log D:\local-agent-backups\scheduled_backup.jsonl --apply-prune
```

For Windows Task Scheduler, first preview the task that would be registered:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_scheduled_backup.ps1 -BackupRoot D:\local-agent-backups -OffMachineRoot E:\local-agent-off-machine-backups -ApplyPrune
```

The preview prints the exact program, arguments, working directory, and daily run time. It does not create a task.

Register or update the task after reviewing the preview:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_scheduled_backup.ps1 -BackupRoot D:\local-agent-backups -OffMachineRoot E:\local-agent-off-machine-backups -ApplyPrune -Register
```

The helper registers:

```text
Task name:
LocalAgentScheduledBackup

Program/script:
D:\local-agent-v1\venv\Scripts\python.exe

Arguments:
scripts\runtime_state.py --env-file .env scheduled-backup ...

Start in:
D:\local-agent-v1
```

Use `-At 02:30` to change the daily run time. Use `-TaskName MyTaskName` if the deployed environment needs a different task name.

Remove the task:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_scheduled_backup.ps1 -Unregister
```

For a production-like setup, put `--off-machine-root` on another disk, network share, or managed mounted storage. A second folder inside the same repo is not an off-machine backup.

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

## Retention Policy

For local development:

- keep at least `7` recent local backups,
- create a backup before every large ingest, parser/chunking change, or storage migration,
- run prune in dry-run mode first,
- apply prune only after confirming the backup root and paths.

For production-like deployments:

- create scheduled daily backups,
- keep local backups for `7` to `14` days,
- copy backups to off-machine storage,
- keep weekly off-machine backups for at least `4` weeks,
- run a restore drill before trusting the policy.

## Safety Rules

- Do not commit files under `var/backups/`.
- Do not restore while another app process owns local Qdrant.
- Keep backup directories outside the repo for long-term storage.
- For production deployment, copy backups to a separate disk or managed storage.
- Use `prune-backups` without `--apply` first; the default dry run is there on purpose.
