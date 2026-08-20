# System Design And Repository Structure

This document describes the target production structure for the local agentic RAG system.

The current application now uses a production-style `src/local_agent` package layout. Remaining production work is mainly around deployment, rollback, monitoring, and optional deeper domain refactoring.

## Current Layout Diagnosis

Current top-level folders:

```text
src/
scripts/
docs/
data/
eval/
tests/
benchmarks/
static/
templates/
```

What is good:

- product code is under `src/local_agent`,
- the core domains are already separated as subpackages,
- docs are split by subsystem,
- regression and eval scripts exist,
- latency benchmark and per-trace performance timings exist,
- local runtime data is mostly ignored by `.gitignore`,
- local runtime backup and restore tooling exists,
- the app can be installed with `pip install -e .`.

What should improve:

- web assets are still top-level instead of owned by the web package,
- deployment and rollback structure is not formal yet,
- a deeper domain refactor could later split `app`, `agent`, and `storage` into clearer `api`, `application`, `infrastructure`, and `tools` packages.

## Target Production Layout

Recommended final structure:

```text
local-agent-v1/
  src/
    local_agent/
      app/
      agent/
      answering/
      evaluation/
      ingestion/
      llm/
      retrieval/
      storage/
      tools/
      observability/
      operations/
  tests/
    unit/
    integration/
    smoke/
  benchmarks/
    gold_qa/
      eval_multi_doc_rag.json
      eval_sora.json
      eval_sora_answers.json
  scripts/
  docs/
  data/
    raw/
    samples/
  var/
    sqlite/
    qdrant/
    logs/
  eval/
    reports/
  deploy/
  pyproject.toml
  README.md
```

This target layout gives each concern a clear owner:

- `src/local_agent`: installable product code,
- `src/local_agent/app`: composition root, CLI/web entrypoints, config, paths, dependency wiring,
- `src/local_agent/llm`: model/provider clients and embedding-cache behavior,
- `src/local_agent/tools`: tool registry, web tools, and MCP-style connectors,
- `src/local_agent/evaluation`: gold QA scoring, feedback eval candidates, and eval runs,
- `src/local_agent/operations`: local operational workflows such as runtime backup and restore,
- `src/local_agent/retrieval`: document routing, hybrid search, context expansion, and routing-cache behavior,
- `src/local_agent/storage`: SQLite runtime metadata, feedback, traces, memory, document ownership, and local inspection helpers,
- `tests`: automated tests only,
- `benchmarks/gold_qa`: versioned evaluation datasets,
- `data/raw`: user/source documents,
- `var`: local runtime state,
- `eval/reports`: generated evaluation outputs,
- `deploy`: production startup and deployment assets.

## Application Layers

The production system should stay layered like this:

```text
Data ingestion
-> chunking
-> indexing and storage
-> document routing
-> retrieval
-> context expansion
-> evidence selection
-> answer generation
-> verification and repair
-> orchestration
-> guardrails and tools
-> memory
-> UI/API/CLI
-> evaluation
-> observability
-> operations
```

## Runtime Flow

RAG question:

```text
user query
-> memory load
-> planner
-> auth document scope when API auth is enabled
-> document router
-> retrieval
-> evidence selection
-> answering service
-> verifier
-> repair or retry if needed
-> trace saved
-> answer returned with citations
```

Tool question:

```text
user query
-> planner
-> tool registry
-> guardrails
-> tool execution if allowed
-> answer from tool output
-> trace saved
```

System status:

```text
UI System tab or GET /api/system/status
-> SQLite health and document count
-> Qdrant health and collection check
-> Ollama chat and embedding model availability
-> tool registry count and approval summary
-> overall ok/degraded/error status
```

Runtime backup:

```text
operator command
-> load configured runtime paths
-> SQLite online backup API
-> copy Qdrant local directory without runtime lock files
-> write backup metadata
-> optional inspect or restore command
```

## Packaging Direction

The project uses a `src/` layout.

The migration included:

- move product packages under `src/local_agent`,
- update imports,
- keep web template/static paths rooted at the project root for now,
- update CLI entry points,
- update eval and regression script paths,
- update docs and commands,
- run regression after the move.

The repo now exposes a production-style CLI entry point:

```powershell
local-agent ask --query "What are the key features of WatchTower?"
```

This is better than relying on:

```powershell
python -m local_agent.app.main ...
```

because the command is independent of source file locations.

## Test And Benchmark Separation

The old `test/` folder used to contain:

- one Python test,
- gold QA JSON files.

The production split is now:

```text
tests/                  automated tests
benchmarks/gold_qa/     versioned eval datasets
data/evals/             generated feedback eval drafts
eval/reports/           generated eval reports
```

This matters because tests and evaluation datasets have different lifecycles. Tests validate code behavior. Gold QA validates answer quality.

## Migration Plan

### Phase 1: Stabilize Entry Points

Status: completed.

- Add `local-agent` console script.
- Add `src/local_agent/app/paths.py` as the central project path registry.
- Prefer `python -m local_agent.app.main` or `local-agent` in docs.
- Keep file-path CLI commands out of docs; use `local-agent` or `python -m local_agent.app.main`.

### Phase 2: Split Tests And Gold QA

Status: completed.

- Python tests moved to `tests/`.
- Gold QA files moved to `benchmarks/gold_qa/`.
- Eval scripts, app path constants, docs, and regression commands now point at the new benchmark path.

### Phase 3: Move To `src/`

Status: completed.

- Product packages moved under `src/local_agent`.
- Existing package groups such as `app`, `agent`, `retrieval`, and `storage` are preserved as subpackages for a safer first migration.
- Imports now use the `local_agent.*` namespace.
- Packaging uses `src` package discovery.
- A deeper domain refactor into `api`, `application`, `infrastructure`, and `tools` can happen after this migration is stable.

### Phase 4: Separate Runtime State

Status: completed for local runtime paths and local backup/restore.

- New default SQLite path is `var/sqlite/app.db`.
- New default Qdrant path is `var/qdrant/`.
- New web startup log path is `var/logs/`.
- Keep `.env.example` aligned with these paths.
- Runtime backup and restore are implemented in `src/local_agent/operations/runtime_backup.py`.
- Operator commands live in `scripts/runtime_state.py`.
- Scheduled backup execution is available through `scripts/runtime_state.py scheduled-backup`.
- Detailed instructions live in [docs/BACKUP_RESTORE.md](BACKUP_RESTORE.md).

### Phase 5: User And Document Isolation

Status: completed for v1 API token namespaces and document visibility.

- API auth creates user/session namespaces for traces, feedback, memory, and tool audit.
- Documents carry `owner_id` and `visibility`.
- Existing indexed documents default to global visibility.
- Authenticated web ingests become user-owned.
- Routing, retrieval, document library, ingestion status, and document-list tool output are scoped to global plus current-user documents.
- Detailed instructions live in [docs/DOCUMENT_ISOLATION.md](DOCUMENT_ISOLATION.md).

### Phase 6: Deployment Shape

Status: started for local single-machine deployment.

- Local deployment documentation lives in [docs/DEPLOYMENT.md](DEPLOYMENT.md).
- Add `deploy/` later if we introduce service-manager, container, or hosted deployment assets.
- Add deployment-specific config examples.
- Production health endpoints for app, SQLite, Qdrant, Ollama, and model availability are started through `/health` and `/api/system/status`.
- Add service-manager/container assets and register the real scheduled backup job for deployed environments.

## Rules For Future Changes

- Keep document-specific answer hacks out of the codebase.
- Keep RAG facts grounded in retrieved chunks, not memory or tools.
- Keep tool execution behind guardrails.
- Add eval coverage before optimizing answer behavior.
- Run latency benchmarks before and after performance changes.
- Run regression before commit.
- Update docs when architecture changes.
