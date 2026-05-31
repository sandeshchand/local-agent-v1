from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DOCUMENTS_DIR = DATA_DIR / "raw" / "documents"
EVAL_CANDIDATES_PATH = DATA_DIR / "evals" / "feedback_eval_candidates.json"

GOLD_QA_DIR = PROJECT_ROOT / "benchmarks" / "gold_qa"
GOLD_EVAL_PATH = GOLD_QA_DIR / "eval_multi_doc_rag.json"

EVAL_OUTPUT_DIR = PROJECT_ROOT / "eval"
DOCS_DIR = PROJECT_ROOT / "docs"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"

VAR_DIR = PROJECT_ROOT / "var"
SQLITE_RUNTIME_DIR = VAR_DIR / "sqlite"
QDRANT_RUNTIME_DIR = VAR_DIR / "qdrant"
LOGS_DIR = VAR_DIR / "logs"
DEFAULT_SQLITE_PATH = SQLITE_RUNTIME_DIR / "app.db"
DEFAULT_QDRANT_PATH = QDRANT_RUNTIME_DIR
