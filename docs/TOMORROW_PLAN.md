# Tomorrow Plan

Use this note to restart the next development session.

## Current State

The latest completed work added local deployment documentation, memory management API/UI, guardrail/tool audit visibility, memory multi-turn evaluation, short-term sensitive-text redaction, local backup/restore tooling, and evidence-selection latency optimization.

## Recommended Feature Order

1. Optimize answer-generation latency
   - Evidence selection is now around 2ms for the sampled Sora queries.
   - Answer generation is now the main consistent latency cost.
   - Consider deterministic extractive shortcuts for complete definition/list answers.
   - Re-run full RAG quality after the change.

2. MCP next-step planning
   - Keep current MCP-style File and SQLite tools read-only.
   - Do not add broad external MCP tools until guardrail audit and UI visibility are stronger.
   - Plan true MCP transport integration only after we choose a concrete external MCP server use case.

3. Broader gold QA
   - Add more eval cases for new daily PDFs.
   - Keep the system general-purpose for unseen documents.

4. Scheduled/off-machine backups
   - Keep local backup/restore as the base.
   - Add a deployment policy for backup location, frequency, retention, and restore drills.

5. Authentication and user isolation design
   - Decide single-user local mode versus multi-user deployment.
   - Define which endpoints need authentication first.

## Best First Task

Start with answer-generation latency. We already have the full RAG gate and evidence-selection speedup; now we need one careful optimization and re-measurement.

## Validation Habit

After each feature:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```

For retrieval or answering changes:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --full --output var\logs\rag_quality_report.json
```
