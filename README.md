# 🚀 Local Agentic RAG System

A local-first **Agentic AI system** that extends traditional RAG into a multi-step, decision-driven pipeline with planning, retrieval, reasoning, and verification.

---

## 🔍 Overview

This project implements an **Agentic Retrieval-Augmented Generation (RAG)** system where the model dynamically decides how to respond instead of following a fixed pipeline.

Unlike traditional RAG (retrieve → generate), this system introduces:

- 🧠 **Planner** → decides execution strategy  
- 🔄 **Orchestrator** → manages multi-step workflow  
- 🔍 **Hybrid Retrieval** → dense + BM25 + reranking  
- 🧪 **Evidence Checking** → ensures relevant context  
- ✅ **Verification Layer** → validates grounded answers  
- 🧰 **Tool Integration** → enables action-based responses  

---

## ⚙️ Architecture Flow

User Query  
→ Planner (decide action)  
→ Retrieval (Hybrid Search + Reranker)  
→ Evidence Filtering  
→ Answer Generation (LLM)  
→ Verification  
→ Final Response  

---

## 🚀 Key Features

- Agentic decision-making instead of static pipelines  
- Hybrid search (semantic + keyword)  
- Cross-encoder reranking for precision  
- Evidence-aware answer generation  
- Grounding and hallucination reduction  
- Modular architecture for extensibility  

---

## 🛠 Tech Stack

- Python  
- FastAPI  
- Qdrant (Vector DB)  
- SQLite (metadata + traces)  
- Ollama (local LLM + embeddings)  

---

## Architecture

The project is organized into modular layers:

- **`app/`** — app entrypoints, configuration, dependency wiring, FastAPI layer
- **`ingestion/`** — PDF parsing, chunking, and indexing
- **`retrieval/`** — embedding, search, context building, answer generation
- **`storage/`** — SQLite and Qdrant access
- **`observability/`** — trace logging and future evaluation hooks
- **`templates/` + `static/`** — web UI

This structure keeps the current system simple while making it easier to evolve into a larger agent-based application.

---

## Current Status

Completed milestones:

- **Milestone 1** — local infrastructure setup
- **Milestone 2** — PDF ingestion and retrieval pipeline
- **Milestone 3** — reusable RAG application core
- **Milestone 3.5** — FastAPI web interface and UI improvements
- **Milestone 4** — planner and orchestrator layer

---

## Repository Structure

```text
local-agent-v1/
├── app/
├── ingestion/
│   └── parsers/
├── retrieval/
├── storage/
├── observability/
├── static/
├── templates/
├── scripts/
├── data/
│   ├── raw/
│   │   └── documents/
│   ├── processed/
│   ├── qdrant/
│   ├── sqlite/
│   └── logs/
├── tests/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md


---

## Prerequisites

Before running the project, make sure you have:

* **Python 3.10+**
* **Git**
* **Ollama installed and running locally**

You will also need two local Ollama models:

* one **chat model**
* one **embedding model**

Example models used in this project:

* `qwen2.5:7b-instruct`
* `nomic-embed-text`

---

## Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd local-agent-v1
```

### 2. Create a virtual environment

#### Windows (Command Prompt)

```bat
python -m venv venv
venv\Scripts\activate
```

#### Windows (PowerShell)

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

#### Linux / macOS

```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install project dependencies

```bash
pip install -e .
```

---

## Ollama Setup

Install Ollama on your machine and make sure it is running locally.

Then pull the required models:

```bash
ollama pull qwen2.5:7b-instruct
ollama pull nomic-embed-text
```

You can change the chat model later depending on your hardware and performance needs.

---

## Environment Setup

Copy the example environment file:

### Windows

```bat
copy .env.example .env
```

### Linux / macOS

```bash
cp .env.example .env
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

### Notes

* `CHAT_MODEL` should be a local Ollama chat model
* `EMBED_MODEL` should be a local Ollama embedding model
* `TOP_K` controls how many chunks are retrieved
* `CHUNK_SIZE` and `CHUNK_OVERLAP` control PDF chunking behavior

---

## Prepare Document Folder

Place your PDFs inside:

```text
data/raw/documents/
```

Example:

```text
data/raw/documents/SORA.pdf
```

---

## Running the Application

### Option 1 — Run the FastAPI web app

Start the server:

```bash
uvicorn app.web:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

From the web UI, you can:

* ingest a PDF file or folder
* browse indexed documents
* ask questions in the chat window

---

### Option 2 — Run from CLI

#### Ingest a file or folder

```bash
python app/main.py ingest --path data/raw/documents
```

#### Ask a question

```bash
python app/main.py ask --query "What is Sora?"
```

#### List indexed documents

```bash
python app/main.py list-docs
```

---

## Recommended First Run

A safe first run looks like this:

1. place one PDF inside `data/raw/documents/`
2. start the FastAPI server
3. ingest that PDF from the UI
4. ask a simple question like:

```text
What is Sora?
```

Then try a more specific question like:

```text
How does Sora represent the visual world?
```

---

## Storage

### SQLite

Used for:

* document registry
* chunk metadata
* trace logging

### Qdrant

Used for:

* vector storage
* semantic search

### Local Filesystem

Used for:

* source PDFs
* local runtime data
* future processed outputs

---

## Current Status

Completed milestones:

* **Milestone 1** — local infrastructure setup
* **Milestone 2** — PDF ingestion and retrieval pipeline
* **Milestone 3** — reusable RAG application core
* **Milestone 3.5** — FastAPI web interface and UI improvements
* **Milestone 4** — planner and orchestrator layer

---

## Troubleshooting

### Ollama timeout during answer generation

If answer generation is slow:

* use a smaller chat model
* reduce `TOP_K`
* reduce context size
* increase Ollama client timeout

### PDF gives weak retrieval results

Possible reasons:

* the PDF is scanned or image-based
* extracted text quality is poor
* chunk size may need tuning

### Frontend loads but chat does not respond

Check:

* FastAPI server is running
* Ollama is running
* the correct models are available
* browser console shows no JavaScript errors

### Database or index looks inconsistent

During development, it is often easiest to reset local state:

#### Windows

```bat
del app.db
rmdir /s /q qdrant_data
mkdir qdrant_data
```

#### Linux / macOS

```bash
rm -f app.db
rm -rf qdrant_data
mkdir -p qdrant_data
```

Then re-ingest your documents.

---

## Roadmap

### Completed

* local infrastructure
* Ollama integration
* Qdrant integration
* SQLite integration
* PDF ingestion pipeline
* semantic retrieval
* answer generation
* FastAPI chat UI
* improved frontend usability
* planner + orchestrator
* direct-answer vs retrieve-only modes
* Reranking
* Evidence check + one retry loop
* Hybrid Retrieval(dense + sparse retrieval)
* Cross-encoder Reranking
* Evidence Judgement & Evidence Selection


### Current focus
* Retrieval Stabilization on single-document evaluation
* Citation quality
* Multi-document retrieval hardening

---

## Retrieval Quality Workflow

Phase 1 focuses on making retrieval measurable before adding larger agent features.

### Sora Retrieval Evaluation

The project includes a focused single-document retrieval benchmark:

```text
test/eval_sora.json
```

It checks whether retrieval returns the expected pages and answer keywords for the SORA PDF.

Run it with:

```powershell
.\venv\Scripts\python.exe scripts\eval_retrieval.py --eval-file test\eval_sora.json --output eval\retrieval_report.json
```

The report is written to:

```text
eval/retrieval_report.json
```

Use this before and after retrieval changes. A good retrieval change should improve or preserve:

* expected page coverage
* expected keyword coverage
* section-title relevance
* citation-ready chunk quality

### Sora Answer Evaluation

After retrieval looks healthy, run the full answer-quality benchmark:

```powershell
.\venv\Scripts\python.exe scripts\eval_answers.py --eval-file test\eval_sora_answers.json --output eval\answer_report.json
```

The report is written to:

```text
eval/answer_report.json
```

This checks:

* required fact coverage
* optional detail coverage
* citation presence
* abstention failures
* unwanted drift

Use retrieval evaluation first, then answer evaluation. If retrieval is high but answer quality is low, tune answer synthesis rather than chunk search.

### Current Retrieval Improvements

The retrieval pipeline now includes:

* query expansion for common Sora/RAG evaluation intents
* hybrid dense + BM25 retrieval
* cross-encoder reranking
* neighbor expansion
* section-aware context expansion
* section-title matched expansion
* dynamic parent-child retrieval: child chunks are used for search, then larger parent context blocks are assembled from neighboring chunks for answer generation
* extractive fallback for supported answers when the local LLM over-abstains

For best results after changing chunking or PDF parsing, reset local indexes and re-ingest:

```powershell
Remove-Item app.db
Remove-Item -Recurse qdrant_data
New-Item -ItemType Directory qdrant_data
.\venv\Scripts\python.exe app\main.py ingest --path data\raw\documents\SORA.pdf
```


### Planned
* MCP integration
* better support for larger document sets
* more advanced UI state and interaction patterns
* Tool-aware routing
* Better Evaluation dashboards

---

## Limitations

Current limitations include:

* optimized mainly for text-based PDFs
* no OCR pipeline yet for scanned/image-only PDFs
* no streaming token output yet
* no authentication or multi-user support
* frontend is still intentionally lightweight
* planner/orchestrator is not implemented yet

---


