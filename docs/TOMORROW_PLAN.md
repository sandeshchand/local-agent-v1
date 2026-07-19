# Tomorrow Plan

Use this note to restart the next development session.

## Current State

The latest completed work added memory management API/UI, guardrail/tool audit visibility, memory multi-turn evaluation, short-term sensitive-text redaction, and local backup/restore tooling.

## Recommended Feature Order

1. Run full RAG and latency baselines
   - Confirm answer quality after the latest UI/API and memory changes.
   - Measure latency before choosing any performance optimization.

2. Production deployment documentation
   - Add `docs/DEPLOYMENT.md`.
   - Cover startup, `.env`, health checks, backup/restore, logs, rollback, and one-server ownership of local Qdrant.

3. MCP next-step planning
   - Keep current MCP-style File and SQLite tools read-only.
   - Do not add broad external MCP tools until guardrail audit and UI visibility are stronger.
   - Plan true MCP transport integration only after we choose a concrete external MCP server use case.

4. Broader gold QA
   - Add more eval cases for new daily PDFs.
   - Keep the system general-purpose for unseen documents.

5. Scheduled/off-machine backups
   - Keep local backup/restore as the base.
   - Add a deployment policy for backup location, frequency, retention, and restore drills.

## Best First Task

Start with full RAG regression and latency baseline. If they pass, commit/push the current feature set before starting another behavior change.

## Validation Habit

After each feature:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```

For retrieval or answering changes:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --full --output var\logs\rag_quality_report.json
```
