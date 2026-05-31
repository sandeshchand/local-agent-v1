# System Design And Repository Structure

This document describes the target production structure for the local agentic RAG system.

The current application works, but the repository still has prototype-style layout decisions. Production readiness needs clean source packaging, separated tests, separated benchmark data, clear runtime storage, and stable operational entry points.

## Current Layout Diagnosis

Current top-level folders:

```text
app/
agent/
ingestion/
retrieval/
storage/
observability/
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

- the core domains are already separated,
- docs are split by subsystem,
- regression and eval scripts exist,
- local runtime data is mostly ignored by `.gitignore`,
- the app can be installed with `pip install -e .`.

What should improve:

- production Python code is at repo root instead of under `src/`,
- tests and gold QA are now split, but code still needs a full `src/` migration,
- web assets are top-level instead of owned by the web package,
- runtime artifacts such as logs, local DBs, and vector stores sit near source code,
- package discovery is manually listed in `pyproject.toml`,
- deployment, backup, restore, and health-check structure is not formal yet.

## Target Production Layout

Recommended final structure:

```text
local-agent-v1/
  src/
    local_agent/
      api/
        web.py
        api_models.py
      cli/
        main.py
        commands.py
      application/
        orchestrator.py
        planner.py
        tool_router.py
        guardrails.py
        memory_manager.py
        verifier.py
        schemas.py
      ingestion/
        pipeline.py
        chunking.py
        file_loader.py
        parsers/
      retrieval/
        answer_service.py
        context_builder.py
        doc_router.py
        evidence_checker.py
        evidence_judge.py
        reranker.py
        search.py
      infrastructure/
        config.py
        bootstrap.py
        dependencies.py
        ollama_client.py
        sqlite_store.py
        qdrant_store.py
      tools/
        registry.py
        weather_tool.py
        mcp_adapter.py
        file_mcp.py
        sqlite_mcp.py
      observability/
        traces.py
      web_assets/
        templates/
        static/
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
-> document router
-> retrieval
-> evidence selection
-> answer service
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

## Packaging Direction

The project should move to a `src/` layout, but not by only creating an empty `src` folder.

Correct migration means:

- move product packages under `src/local_agent`,
- update imports,
- update web template/static paths,
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
python app\main.py ...
```

because the command can survive a later `src/` migration.

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

Status: started.

- Add `local-agent` console script.
- Add `app/paths.py` as the central project path registry.
- Prefer `python -m app.main` or `local-agent` in docs.
- Keep old file-path CLI commands working during migration.

### Phase 2: Split Tests And Gold QA

Status: completed.

- Python tests moved to `tests/`.
- Gold QA files moved to `benchmarks/gold_qa/`.
- Eval scripts, app path constants, docs, and regression commands now point at the new benchmark path.

### Phase 3: Move To `src/`

- Move product code under `src/local_agent`.
- Convert imports from package groups such as `app`, `agent`, `retrieval`, and `storage` into the new namespace.
- Update packaging to use package discovery from `src`.
- Update web template/static loading.
- Run full regression.

### Phase 4: Separate Runtime State

Status: started.

- New default SQLite path is `var/sqlite/app.db`.
- New default Qdrant path is `var/qdrant/`.
- New web startup log path is `var/logs/`.
- Keep `.env.example` aligned with these paths.
- Document backup and restore.

### Phase 5: Deployment Shape

- Add `deploy/` with process, environment, and health-check docs.
- Add deployment-specific config examples.
- Add production health endpoints for app, SQLite, Qdrant, Ollama, and model availability.

## Rules For Future Changes

- Keep document-specific answer hacks out of the codebase.
- Keep RAG facts grounded in retrieved chunks, not memory or tools.
- Keep tool execution behind guardrails.
- Add eval coverage before optimizing answer behavior.
- Run regression before commit.
- Update docs when architecture changes.
