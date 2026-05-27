# Regression Checks

Use the regression runner before commits and before pushing risky changes.

This is a local script. It does not require a File MCP server.

## Default Check

Run:

```cmd
venv\Scripts\python.exe scripts\run_regression.py
```

Default behavior:

- Python compile checks for core app, agent, retrieval, and smoke-test files.
- Memory smoke test.
- Guardrails smoke test.
- MCP adapter smoke test.
- Weather tool smoke test.
- Focused RAG quality eval.

Focused RAG eval currently covers:

- `docker_lazydocker_features`
- `docker_watchtower_features`
- `ml_crfs`
- `sora_world_simulator`

## Quick Check

Run compile and smoke checks only:

```cmd
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```

Use this during small edits when the RAG pipeline is not touched.

## Full Benchmark

Run the full multi-document RAG benchmark:

```cmd
venv\Scripts\python.exe scripts\run_regression.py --full --output eval\rag_quality_report.json
```

Use this before bigger pushes, retrieval changes, answer-service changes, or ingestion/chunking changes.

## Custom Focused Eval

Run selected gold QA items:

```cmd
venv\Scripts\python.exe scripts\run_regression.py --ids docker_watchtower_features,ml_crfs
```

## What This Does Not Cover Yet

- Live weather API calls.
- Live MCP server execution.
- UI rendering.
- Full browser tests.

Those should be added when those layers become more important.
