# Local Agentic RAG System

A local-first Agentic Retrieval-Augmented Generation system for asking grounded questions over multiple PDF documents.

The project now supports multi-PDF ingestion, document routing, hybrid retrieval, answer generation, verification, answer repair, short-term and long-term memory, trace logging, and repeatable RAG quality evaluation.

## Current Status

Completed:

- Local Ollama chat and embedding integration
- SQLite metadata, conversation memory, and trace storage
- Long-term project memory with relevance-ranked retrieval
- Qdrant vector storage
- PDF parsing, cleanup, chunking, and ingestion
- Multi-document indexing
- Planner and stronger orchestration layer with verification-aware retrieval retry
- Document router for multi-PDF questions
- Hybrid retrieval: dense search plus BM25
- Cross-encoder reranking
- Neighbor and parent-context expansion
- Evidence selection
- Grounded answer generation
- Generic source-window extraction for feature, setup, formula, example, and reason questions
- Generic verifier
- Answer repair after verifier failure
- Tool-call guardrails with allow, deny, and needs-approval decisions
- Read-only current weather web tool
- Multi-document gold QA evaluation
- Optional OCR path for scanned/image-only PDFs
- CLI memory inspection and manual memory creation

Still in progress:

- Memory-specific multi-turn evaluation
- Optional semantic/vector memory retrieval
- Better citation polish
- Larger benchmark coverage across new daily PDFs
- Stronger regression gates before every code change
- Optional dashboard for evaluation reports

## Architecture Flow

```text
User query
-> MemoryManager
   -> save user turn
   -> capture explicit long-term memory
   -> load relevant project/session memory
-> Planner
-> ToolRouter
   -> guardrails when a tool call is selected
   -> current weather web tool for weather/current-temperature questions
-> DocumentRouter
-> RetrievalService
   -> dense vector search
   -> BM25 sparse search
   -> RRF fusion
   -> cross-encoder reranking
   -> context expansion
-> EvidenceJudge
-> AnswerService
-> Verifier
-> optional Answer Repair
-> optional full-corpus retrieval retry
-> Trace saved to SQLite
-> Final answer with citations
```

## Repository Structure

```text
app/          FastAPI, CLI, config, dependency wiring
agent/        planner, tool router, orchestrator, verifier, memory
ingestion/    PDF parsing, cleanup, chunking, indexing
retrieval/    search, reranking, routing, evidence, answer generation
storage/      SQLite and Qdrant adapters
scripts/      ingestion/evaluation helper scripts
test/         gold QA and evaluation datasets
eval/         generated evaluation reports
data/         local source PDFs
```

## Setup

Create and activate the virtual environment.

Command Prompt:

```cmd
python -m venv venv
venv\Scripts\activate
```

PowerShell:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

Install the project:

```cmd
pip install -e .
```

Optional OCR support for scanned PDFs:

```cmd
pip install -e .[ocr]
```

OCR also requires Tesseract OCR and Poppler installed on the machine.

Pull local Ollama models:

```cmd
ollama pull qwen2.5:7b-instruct
ollama pull nomic-embed-text
```

Create `.env`:

```cmd
copy .env.example .env
```

Example `.env`:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
CHAT_MODEL=qwen2.5:7b-instruct
EMBED_MODEL=nomic-embed-text
QDRANT_PATH=./qdrant_data
SQLITE_PATH=./app.db
TOP_K=3
CHUNK_SIZE=800
CHUNK_OVERLAP=120
DEBUG=true
```

## Ingest PDFs

Place PDFs under:

```text
data/raw/documents/
```

Ingest all documents:

```cmd
venv\Scripts\python.exe app\main.py ingest --path data\raw\documents
```

List indexed documents:

```cmd
venv\Scripts\python.exe app\main.py list-docs
```

Ask from command line:

```cmd
venv\Scripts\python.exe app\main.py ask --query "What are the key features of WatchTower?"
```

## Memory

The memory layer has two parts:

- Short-term memory: recent conversation turns for the active session.
- Long-term memory: durable project rules, user preferences, task status, evaluation results, and known issues.

Memory is used as project/user guidance. It is not treated as PDF evidence. RAG answers must still use retrieved document context and citations.

Manually add a memory:

```cmd
venv\Scripts\python.exe app\main.py remember --content "Do not use document-specific hardcoded keywords." --kind project_decision --importance 3
```

List stored memory:

```cmd
venv\Scripts\python.exe app\main.py list-memory
```

Run the memory smoke test:

```cmd
venv\Scripts\python.exe scripts\smoke_memory.py
```

Detailed implementation notes:

```text
docs/MEMORY.md
```

## Answer Service

The grounded answer layer is implemented in:

```text
retrieval/answer_service.py
```

It combines LLM answer generation with generic deterministic extractors for feature, limitation, definition, pipeline, command, example, why, and list-style questions. It also handles citation cleanup and verifier repair fallbacks.

Detailed implementation notes:

```text
docs/ANSWER_SERVICE.md
```

## Guardrails

Tool-call guardrails protect actions before any registered tool executes.

Current behavior:

- registered tools with `requires_approval=False` are allowed,
- unknown or missing tool calls are denied,
- registered tools with `requires_approval=True` return `needs_approval` unless explicitly approved for the current request,
- every decision is recorded as a `guardrail` trace step.

Approve a tool for one CLI request:

```cmd
venv\Scripts\python.exe app\main.py ask --query "Run the approved tool" --approve-tool tool_name
```

Detailed implementation notes:

```text
docs/GUARDRAILS.md
```

## Web Tools

The first web-based tool is:

```text
get_current_weather
```

It answers current weather questions for a named location using a read-only weather API. It is tool context, not PDF citation evidence.

Example:

```cmd
venv\Scripts\python.exe app\main.py ask --query "What is the current weather in Berlin?"
```

Detailed implementation notes:

```text
docs/WEB_TOOLS.md
```

Run the web app:

```cmd
uvicorn app.web:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## Gold QA Evaluation

The current multi-document gold QA file is:

```text
test/eval_multi_doc_rag.json
```

It currently contains 45 questions across Sora, Docker, machine-learning, Python, AI coding, Pydantic, SmolDocling/OCR, introduction, and AI side-hustle PDFs. Each item contains:

- `question`
- `expected_doc_title`
- `expected_answer`
- `must_have`
- `should_have`
- `must_not_have`

Run the full benchmark:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --eval-file test\eval_multi_doc_rag.json --output eval\rag_quality_report.json
```

Run selected questions while debugging:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --ids docker_watchtower_features,ml_crfs
```

Use as a quality gate:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --fail-under-average 8 --fail-under-item 7
```

Scoring combines:

- required fact coverage
- optional detail coverage
- citation presence
- correct document routing
- verifier status
- unwanted drift

Target:

- Average score should stay above `8/10`.
- Each important item should stay above `7/10`.
- New PDFs should add at least 3-5 gold questions.

Latest recorded baseline:

- Date: 2026-05-20
- Average score: `9.45/10`
- Passed: `45/45` items at `>= 8/10`
- Gate result: passed `--fail-under-average 8 --fail-under-item 7`
- Remaining weak areas: exact optional details in a few answers, citation polish, and memory-specific multi-turn evaluation.

## How To Add Gold QA For A New PDF

For each new document, add questions to `test/eval_multi_doc_rag.json`:

1. Definition question: what is the main concept/tool/model?
2. Feature question: what are the key features/components?
3. How/why question: mechanism or reason.
4. Limitation question: risks, constraints, weaknesses.
5. Comparison/application question if the paper supports it.

Use `must_have` for facts that must appear in a good answer. Use `should_have` for helpful but optional facts. Use `must_not_have` for likely drift from other PDFs.

## Orchestration Layer

The orchestration layer is implemented in:

```text
agent/orchestrator.py
```

It currently performs:

- session memory save/load
- long-term memory capture and relevance-ranked memory loading
- planning
- direct-answer routing for casual messages
- retrieval routing for document questions
- document routing across multiple PDFs
- retrieval and evidence selection
- answer generation
- verification
- answer repair when verification fails
- one generic full-corpus retrieval retry when the first answer has no citations or still fails verification
- tool-call guardrail decisions before tool execution
- trace saving to SQLite

Detailed implementation notes:

```text
docs/ORCHESTRATION.md
```

Current implementation roadmap:

```text
docs/NEXT_STEPS.md
```

Smoke checks:

```cmd
venv\Scripts\python.exe app\main.py ask --query "hi"
venv\Scripts\python.exe app\main.py ask --query "What are the key features of WatchTower?"
venv\Scripts\python.exe app\main.py ask --query "What are Conditional Random Fields used for?"
```

Expected behavior:

- `hi` should use `direct_answer`.
- PDF questions should use `retrieve_only`.
- Retrieved answers should include citations.
- `verification.status` should normally be `verified`.
- Trace steps should include a `memory` step with captured and loaded memory counts.

## Reset Local Index

Only reset when chunking/parsing changes or the DB/index is inconsistent.

Command Prompt:

```cmd
ren app.db app.old.db
ren qdrant_data qdrant_data_old
mkdir qdrant_data
venv\Scripts\python.exe app\main.py ingest --path data\raw\documents
```

PowerShell:

```powershell
Rename-Item app.db app.old.db
Rename-Item qdrant_data qdrant_data_old
New-Item -ItemType Directory qdrant_data
.\venv\Scripts\python.exe app\main.py ingest --path data\raw\documents
```

## Evaluation Process We Follow

1. Add/update gold QA first.
2. Run targeted eval for failing cases with `--ids`.
3. Fix retrieval, evidence selection, answer generation, or verifier depending on the failure.
4. Run full benchmark.
5. Accept the change only if quality stays above the gate.

Use the report fields:

- `missing_must_have`: answer missed required facts.
- `triggered_must_not_have`: answer drifted into wrong content.
- `top_routed_doc`: document router selected the wrong PDF.
- `verification`: verifier/grounding issues.
- `answer`: inspect the actual generated answer.

## Known Limitations

- Scanned PDFs require optional OCR dependencies plus local Tesseract/Poppler installs.
- Medium-style PDFs can still contain noisy boilerplate.
- Local LLM output can vary between runs.
- Some answer polish and citation formatting still need work.
- Evaluation is only as good as the gold QA coverage.

## Next Engineering Steps

1. Add memory-specific multi-turn eval tests.
2. Add 3-5 gold QA questions for every new daily PDF.
3. Add a small regression command that runs before every commit.
4. Improve citation formatting and remove duplicated citation text.
5. Add guardrails before tool execution and external integrations.
6. Add a simple evaluation summary dashboard or HTML report.
