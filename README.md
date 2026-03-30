# Local Agent V1

Local Agent V1 is a local-first AI assistant for interacting with PDF documents through semantic search and chat.

It is built with:

- **Ollama** for local LLM inference and embeddings
- **Qdrant** for vector search
- **SQLite** for metadata and trace storage
- **FastAPI** for the web interface
- a modular architecture designed for future **agent orchestration** and **MCP integration**

## Current Features

- PDF ingestion from a file or folder
- Text chunking and embedding
- Semantic retrieval over indexed documents
- Chat interface through FastAPI
- Source citations in responses
- Indexed document listing
- Query trace storage for debugging and evaluation

## Project Goal

The goal of this project is to build a fully local, modular AI system that can evolve from a simple PDF RAG assistant into an agentic application with planning, tool use, and MCP-based integrations.

## Tech Stack

- Python
- Ollama
- Qdrant
- SQLite
- FastAPI
- PyPDF

## Status

Milestones completed so far:

- Milestone 1: local infrastructure setup
- Milestone 2: PDF ingestion and retrieval pipeline
- Milestone 3: reusable RAG app core
- Milestone 3.5: FastAPI web interface

Milestone 4 will introduce planner and orchestrator support.