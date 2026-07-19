# Regression Checks

Use the regression runner before commits and before pushing risky changes.

This is a local script. It uses in-process read-only MCP smoke tests and does not require an external MCP server.

## Default Check

Run:

```cmd
venv\Scripts\python.exe scripts\run_regression.py
```

Default behavior:

- Python compile checks for core app, agent, retrieval, and smoke-test files.
- Memory smoke test.
- SQLite threading smoke test for serialized store access.
- Document library pagination/search smoke test.
- Guardrails smoke test.
- File MCP smoke test.
- SQLite MCP smoke test.
- MCP adapter smoke test.
- Tool approval UI smoke test.
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
venv\Scripts\python.exe scripts\run_regression.py --full --output var\logs\rag_quality_report.json
```

Use this before bigger pushes, retrieval changes, answer-service changes, or ingestion/chunking changes.

When using local Qdrant path mode, stop the web server before running the full benchmark. Only one process can own the local Qdrant folder at a time. If the benchmark says the storage folder is already accessed, stop old `uvicorn`, `run_regression.py`, or `eval_rag_quality.py` processes and run the command again.

Detailed scoring notes are in:

```text
docs/EVALUATION.md
```

## Latency Benchmark

Run this when you are working on performance:

```cmd
venv\Scripts\python.exe scripts\benchmark_latency.py --limit 5 --output var\logs\latency_benchmark_report.json
```

This is separate from the default regression runner because it depends on real model speed and machine load. Use it to compare before and after reports when changing retrieval, reranking, planner behavior, model settings, or context size.

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
