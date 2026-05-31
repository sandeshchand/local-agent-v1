# Local Agentic RAG System

Local-first agentic RAG for grounded question answering over many PDF documents.

The system is designed for multi-document retrieval quality, visible traces, repeatable evaluation, and safe local tool use. It currently supports PDF ingestion, hybrid retrieval, document routing, answer verification, answer repair, memory, guarded tools, MCP-style local connectors, feedback analytics, and a web UI for trace inspection.

This repo is not treated as a toy demo. The engineering target is a production-ready local RAG application with measurable quality gates and clear operational controls.

## Core Capabilities

- Multi-PDF ingestion with cleaned, metadata-rich chunks.
- Hybrid retrieval with dense search, BM25, fusion, reranking, and context expansion.
- Document routing to reduce wrong-document answers in large collections.
- Evidence-grounded answer generation with citations.
- Answer verification, repair, and retrieval retry when quality fails.
- Short-term conversation memory and long-term project/user memory.
- Tool-call guardrails with `allow`, `deny`, and `needs_approval`.
- MCP-style read-only File and SQLite connectors.
- Read-only weather tool for current weather questions.
- Web UI with trace view, source inspection, feedback, eval drafts, and tool visibility.
- Gold QA evaluation and regression commands for quality control.

## Architecture

```text
PDFs / files
-> ingestion and chunking
-> vector + metadata storage
-> document routing
-> hybrid retrieval
-> evidence selection
-> answer generation
-> verification
-> answer repair or retrieval retry
-> trace and feedback storage
-> UI / API / CLI
```

Tool requests follow a separate guarded path:

```text
planner
-> tool registry
-> guardrails
-> approved read-only tool or MCP-style connector
-> tool answer
-> trace
```

Memory is used only as project/user guidance. It is not PDF evidence. PDF answers must still come from retrieved document chunks and citations.

## Quick Start

Create and activate the virtual environment.

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

Install the project.

```powershell
pip install -e .
```

Optional OCR support for scanned PDFs:

```powershell
pip install -e .[ocr]
```

Pull local Ollama models.

```powershell
ollama pull qwen2.5:7b-instruct
ollama pull nomic-embed-text
```

Create local config.

```powershell
copy .env.example .env
```

Common `.env` values:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
CHAT_MODEL=qwen2.5:7b-instruct
EMBED_MODEL=nomic-embed-text
QDRANT_PATH=./var/qdrant
SQLITE_PATH=./var/sqlite/app.db
TOP_K=3
DEBUG=true
```

## Ingest And Ask

Put PDFs under:

```text
data/raw/documents/
```

Ingest all PDFs:

```powershell
local-agent ingest --path data\raw\documents
```

Ask from the CLI:

```powershell
local-agent ask --query "What are the key features of WatchTower?"
```

List indexed documents:

```powershell
local-agent list-docs
```

## Run The Web UI

Use the helper script so only one local server owns the app and Qdrant path.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_web.ps1
```

Open:

```text
http://127.0.0.1:8000
```

Do not run a second `uvicorn app.web:app` process from another Python installation. The helper starts the server from `venv` and writes logs to:

```text
var/logs/web.out.log
var/logs/web.err.log
```

## Quality Gates

Run the standard regression gate before committing important changes:

```powershell
venv\Scripts\python.exe scripts\run_regression.py
```

Run compile and smoke checks only:

```powershell
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```

Run the full RAG benchmark:

```powershell
venv\Scripts\python.exe scripts\eval_rag_quality.py --eval-file benchmarks\gold_qa\eval_multi_doc_rag.json --output eval\rag_quality_report.json --fail-under-average 8 --fail-under-item 7
```

Quality rules:

- Add 3 to 5 gold QA items for every important new PDF.
- Keep average eval score above `8/10`.
- Keep important individual questions above `7/10`.
- Inspect failed items by `missing_must_have`, `triggered_must_not_have`, `top_routed_doc`, `verification`, and `answer`.

## Operations

Useful CLI commands:

```powershell
local-agent ask --query "hi"
local-agent ask --query "List database tables"
local-agent ask --query "Read file docs/MCP.md"
local-agent ask --query "What is the current weather in Berlin?"
local-agent list-memory
```

Reset the local index only when parsing, chunking, or storage is inconsistent. See [docs/CHUNKING.md](docs/CHUNKING.md) and [docs/REGRESSION.md](docs/REGRESSION.md) before resetting.

## Production Readiness

Already implemented:

- repeatable local regression command,
- gold QA benchmark,
- trace storage,
- feedback collection,
- answer verification and repair,
- guarded tool execution,
- read-only local file/database connectors,
- documented architecture and subsystem behavior.

Required before real production use:

- authentication and user/session isolation,
- secrets management outside `.env` for deployed environments,
- backup and restore plan for SQLite and Qdrant data,
- deployment/container strategy,
- monitoring and alerting,
- stronger permission model for any future write/delete tools,
- larger benchmark coverage for unseen document families,
- explicit data retention and privacy policy.

Detailed checklist: [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md)

## Documentation Map

Architecture and orchestration:

- [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md)
- [docs/ORCHESTRATION.md](docs/ORCHESTRATION.md)
- [docs/PLANNER.md](docs/PLANNER.md)
- [docs/DOCUMENT_ROUTER.md](docs/DOCUMENT_ROUTER.md)

Retrieval and answers:

- [docs/CHUNKING.md](docs/CHUNKING.md)
- [docs/ANSWER_SERVICE.md](docs/ANSWER_SERVICE.md)
- [docs/ANSWER_VERIFICATION.md](docs/ANSWER_VERIFICATION.md)
- [docs/ANSWER_REPAIR.md](docs/ANSWER_REPAIR.md)

Tools, guardrails, and memory:

- [docs/GUARDRAILS.md](docs/GUARDRAILS.md)
- [docs/MCP.md](docs/MCP.md)
- [docs/WEB_TOOLS.md](docs/WEB_TOOLS.md)
- [docs/MEMORY.md](docs/MEMORY.md)

Evaluation, UI, and roadmap:

- [docs/EVALUATION.md](docs/EVALUATION.md)
- [docs/REGRESSION.md](docs/REGRESSION.md)
- [docs/UI_TRACE_VIEW.md](docs/UI_TRACE_VIEW.md)
- [docs/FEEDBACK_ANALYTICS.md](docs/FEEDBACK_ANALYTICS.md)
- [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md)
- [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md)
