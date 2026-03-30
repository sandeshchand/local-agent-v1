# Local Agent V1

A local-first PDF RAG assistant built with **Ollama**, **Qdrant**, **SQLite**, and **FastAPI**.

Local Agent V1 lets you ingest PDF documents, search them semantically, and chat with them through a simple web interface — all while keeping inference and storage on your own machine.

The project is designed as a modular foundation for future **planner/orchestrator logic**, **agent workflows**, and **MCP-based tool integration**.

---

## Highlights

- **Local-first** architecture
- **PDF ingestion** from a single file or an entire folder
- **Semantic retrieval** over indexed document chunks
- **Chat interface** powered by FastAPI
- **Source citations** in responses
- **SQLite-backed metadata and trace storage**
- **Qdrant vector search**
- **Ollama-based local LLM + embeddings**
- Built with a clean architecture for future agentic expansion

---

## Demo Scope

Current capabilities include:

- Indexing PDFs into a local vector database
- Asking grounded questions over indexed documents
- Viewing indexed documents in a web UI
- Tracking query traces for debugging and iteration

This repository currently focuses on a strong **local RAG core** before introducing more advanced agentic features.

---

## Tech Stack

- **Python**
- **Ollama** — local model serving and embeddings
- **Qdrant** — vector database
- **SQLite** — metadata and trace storage
- **FastAPI** — web backend and API layer
- **PyPDF** — PDF text extraction

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

Next milestone:

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