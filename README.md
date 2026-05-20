# Local Agentic RAG System

A local-first Agentic Retrieval-Augmented Generation system for asking grounded questions over multiple PDF documents.

The project now supports multi-PDF ingestion, document routing, hybrid retrieval, answer generation, verification, answer repair, trace logging, and repeatable RAG quality evaluation.

## Current Status

Completed:

- Local Ollama chat and embedding integration
- SQLite metadata, conversation memory, and trace storage
- Qdrant vector storage
- PDF parsing, cleanup, chunking, and ingestion
- Multi-document indexing
- Planner and orchestration layer
- Document router for multi-PDF questions
- Hybrid retrieval: dense search plus BM25
- Cross-encoder reranking
- Neighbor and parent-context expansion
- Evidence selection
- Grounded answer generation
- Generic source-window extraction for feature, setup, formula, example, and reason questions
- Generic verifier
- Answer repair after verifier failure
- Multi-document gold QA evaluation
- Optional OCR path for scanned/image-only PDFs

Still in progress:

- Better citation polish
- Larger benchmark coverage across new daily PDFs
- Stronger regression gates before every code change
- Optional dashboard for evaluation reports

## Architecture Flow

```text
User query
-> Planner
-> ToolRouter
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
- Average score: `8.92/10`
- Passed: `40/45` items at `>= 8/10`
- Gate result: passed `--fail-under-average 8 --fail-under-item 7`
- Remaining weak areas: exact optional details in a few answers, citation polish, and occasional verifier false positives.

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
- planning
- direct-answer routing for casual messages
- retrieval routing for document questions
- document routing across multiple PDFs
- retrieval and evidence selection
- answer generation
- verification
- answer repair when verification fails
- trace saving to SQLite

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

1. Add 3-5 gold QA questions for every new daily PDF.
2. Add a small regression command that runs before every commit.
3. Improve citation formatting and remove duplicated citation text.
4. Reduce remaining verifier false positives on valid multi-entity answers.
5. Add a simple evaluation summary dashboard or HTML report.
