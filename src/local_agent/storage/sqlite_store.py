from __future__ import annotations

from collections.abc import Callable
from functools import wraps
import sqlite3
import threading
from pathlib import Path
from typing import Any, TypeVar, cast


F = TypeVar("F", bound=Callable[..., Any])


def _locked(method: F) -> F:
    """Serialize access to the shared SQLite connection."""

    @wraps(method)
    def wrapper(self: "SQLiteStore", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return cast(F, wrapper)


FEEDBACK_ISSUE_TYPES = {
    "",
    "wrong_document",
    "bad_retrieval",
    "weak_answer",
    "missing_citation",
    "tool_issue",
    "other",
}

DOCUMENT_VISIBILITIES = {"global", "user"}


def normalize_document_owner_id(owner_id: str | None) -> str:
    normalized = " ".join((owner_id or "global").strip().split())
    return normalized[:80] if normalized else "global"


def normalize_document_visibility(visibility: str | None) -> str:
    normalized = (visibility or "global").strip().lower()
    if normalized not in DOCUMENT_VISIBILITIES:
        allowed = ", ".join(sorted(DOCUMENT_VISIBILITIES))
        raise ValueError(f"document visibility must be one of: {allowed}")
    return normalized


def document_visible_to(document: dict[str, Any], owner_id: str | None) -> bool:
    if owner_id is None:
        return True
    owner = normalize_document_owner_id(owner_id)
    document_owner = normalize_document_owner_id(document.get("owner_id"))
    visibility = normalize_document_visibility(document.get("visibility"))
    return visibility == "global" or document_owner == owner


def _quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) + chr(34))}"'


def _sqlite_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, str) and len(value) > 500:
        return f"{value[:500]}..."
    return value


def normalize_feedback_issue_type(issue_type: str | None) -> str:
    normalized = (issue_type or "").strip()
    if normalized not in FEEDBACK_ISSUE_TYPES:
        allowed = ", ".join(sorted(item or "none" for item in FEEDBACK_ISSUE_TYPES))
        raise ValueError(f"issue_type must be one of: {allowed}")
    return normalized


class SQLiteStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    def connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._connection is None:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self._connection = sqlite3.connect(
                    str(self.db_path),
                    check_same_thread=False,
                    timeout=30,
                )
                self._connection.row_factory = sqlite3.Row
        return self._connection

    @_locked
    def initialize(self) -> None:
        conn = self.connect()

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS healthcheck (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL UNIQUE,
                title TEXT,
                page_count INTEGER NOT NULL,
                checksum TEXT NOT NULL,
                owner_id TEXT NOT NULL DEFAULT 'global',
                visibility TEXT NOT NULL DEFAULT 'global',
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        document_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(documents)").fetchall()
        }
        document_column_defaults = {
            "owner_id": "TEXT NOT NULL DEFAULT 'global'",
            "visibility": "TEXT NOT NULL DEFAULT 'global'",
            "ingestion_status": "TEXT NOT NULL DEFAULT 'indexed'",
            "parser_version": "TEXT NOT NULL DEFAULT ''",
            "chunking_version": "TEXT NOT NULL DEFAULT ''",
            "embedding_model": "TEXT NOT NULL DEFAULT ''",
            "chunk_size": "INTEGER NOT NULL DEFAULT 0",
            "chunk_overlap": "INTEGER NOT NULL DEFAULT 0",
            "chunk_count": "INTEGER NOT NULL DEFAULT 0",
            "ingest_started_at": "TIMESTAMP",
            "ingest_completed_at": "TIMESTAMP",
            "last_ingest_error": "TEXT NOT NULL DEFAULT ''",
        }
        for column_name, column_sql in document_column_defaults.items():
            if column_name not in document_columns:
                conn.execute(
                    f"""
                    ALTER TABLE documents
                    ADD COLUMN {column_name} {column_sql}
                    """
                )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_ingestion_status (
                source_path TEXT PRIMARY KEY,
                doc_id TEXT,
                title TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                parser_version TEXT NOT NULL DEFAULT '',
                chunking_version TEXT NOT NULL DEFAULT '',
                embedding_model TEXT NOT NULL DEFAULT '',
                chunk_size INTEGER NOT NULL DEFAULT 0,
                chunk_overlap INTEGER NOT NULL DEFAULT 0,
                checksum TEXT NOT NULL DEFAULT '',
                page_count INTEGER NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error TEXT NOT NULL DEFAULT ''
            )
            """
        )
        status_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(document_ingestion_status)").fetchall()
        }
        status_column_defaults = {
            "owner_id": "TEXT NOT NULL DEFAULT 'global'",
            "visibility": "TEXT NOT NULL DEFAULT 'global'",
        }
        for column_name, column_sql in status_column_defaults.items():
            if column_name not in status_columns:
                conn.execute(
                    f"""
                    ALTER TABLE document_ingestion_status
                    ADD COLUMN {column_name} {column_sql}
                    """
                )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                text TEXT NOT NULL,
                token_estimate INTEGER NOT NULL,
                FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
        )
        """)
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(chunks)").fetchall()
        }
        if "section_title" not in columns:
            conn.execute(
                """
                ALTER TABLE chunks 
                ADD COLUMN section_title TEXT
                """
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_turns (
                turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_items (
                memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL DEFAULT 'global',
                scope TEXT NOT NULL DEFAULT 'global',
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                importance REAL NOT NULL DEFAULT 1.0,
                access_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed_at TIMESTAMP,
                UNIQUE(scope, session_id, kind, content)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_items_scope_session
            ON memory_items(scope, session_id, kind)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS traces (
                trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL DEFAULT 'default',
                query TEXT NOT NULL,
                top_k INTEGER NOT NULL,
                retrieved_json TEXT NOT NULL,
                final_answer TEXT NOT NULL,
                steps_json TEXT NOT NULL DEFAULT '[]',
                tool_results_json TEXT NOT NULL  DEFAULT '[]',
                verification_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS answer_feedback (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id INTEGER NOT NULL UNIQUE,
                rating TEXT NOT NULL CHECK (rating IN ('like', 'dislike')),
                issue_type TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'web',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
            )
            """
        )
        feedback_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(answer_feedback)").fetchall()
        }
        if "issue_type" not in feedback_columns:
            conn.execute(
                """
                ALTER TABLE answer_feedback
                ADD COLUMN issue_type TEXT NOT NULL DEFAULT ''
                """
            )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_documents_owner_visibility
            ON documents(owner_id, visibility)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_document_ingestion_owner_visibility
            ON document_ingestion_status(owner_id, visibility)
            """
        )

        conn.commit()

    @_locked
    def ensure_session(self, session_id: str) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT  INTO sessions (session_id)
            VALUES (?)
            ON CONFLICT(session_id) DO UPDATE SET
                updated_at = CURRENT_TIMESTAMP
            """,
            (session_id,))
        conn.commit()

    @_locked
    def insert_conversation_turn(self, session_id: str, role: str, content: str) -> None:
        conn = self.connect()
        self.ensure_session(session_id)
        conn.execute(
            """
            INSERT INTO conversation_turns (session_id, role, content)
            VALUES (?, ?, ?)
            """,
            (session_id, role, content)
        )
        conn.commit()

    @_locked
    def get_recent_conversations(self, session_id: str, limit: int = 6) -> list[dict[str, Any]]:
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT role, content, created_at
            FROM conversation_turns
            WHERE session_id= ?
            ORDER BY turn_id DESC
            LIMIT ?
            """,
            (session_id,limit,)
        ).fetchall()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in reversed(rows)
        ]

    @_locked
    def insert_memory_item(
        self,
        *,
        content: str,
        kind: str,
        session_id: str = "global",
        scope: str = "global",
        source: str = "manual",
        importance: float = 1.0,
    ) -> int:
        conn = self.connect()
        normalized_content = " ".join(content.split())
        normalized_session = session_id or "global"
        normalized_scope = scope or "global"
        conn.execute(
            """
            INSERT INTO memory_items (session_id, scope, kind, content, source, importance)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope, session_id, kind, content) DO UPDATE SET
                source = excluded.source,
                importance = MAX(memory_items.importance, excluded.importance),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                normalized_session,
                normalized_scope,
                kind,
                normalized_content,
                source,
                importance,
            ),
        )
        row = conn.execute(
            """
            SELECT memory_id
            FROM memory_items
            WHERE scope = ? AND session_id = ? AND kind = ? AND content = ?
            """,
            (normalized_scope, normalized_session, kind, normalized_content),
        ).fetchone()
        conn.commit()
        return int(row["memory_id"])

    @_locked
    def list_memory_items(
        self,
        *,
        session_id: str = "default",
        include_global: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conn = self.connect()
        if include_global:
            rows = conn.execute(
                """
                SELECT memory_id, session_id, scope, kind, content, source, importance,
                       access_count, created_at, updated_at, last_accessed_at
                FROM memory_items
                WHERE scope = 'global'
                   OR (scope = 'session' AND session_id = ?)
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT memory_id, session_id, scope, kind, content, source, importance,
                       access_count, created_at, updated_at, last_accessed_at
                FROM memory_items
                WHERE scope = 'session' AND session_id = ?
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [self._memory_row_to_dict(row) for row in rows]

    @_locked
    def delete_memory_item(self, memory_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        item = self.get_memory_item(memory_id)
        if item is None:
            return None

        conn.execute("DELETE FROM memory_items WHERE memory_id = ?", (memory_id,))
        conn.commit()
        return item

    @_locked
    def get_memory_item(self, memory_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute(
            """
            SELECT memory_id, session_id, scope, kind, content, source, importance,
                   access_count, created_at, updated_at, last_accessed_at
            FROM memory_items
            WHERE memory_id = ?
            """,
            (memory_id,),
        ).fetchone()
        if row is None:
            return None
        return self._memory_row_to_dict(row)

    @_locked
    def touch_memory_items(self, memory_ids: list[int]) -> None:
        if not memory_ids:
            return
        conn = self.connect()
        conn.executemany(
            """
            UPDATE memory_items
            SET access_count = access_count + 1,
                last_accessed_at = CURRENT_TIMESTAMP
            WHERE memory_id = ?
            """,
            [(memory_id,) for memory_id in memory_ids],
        )
        conn.commit()

    def _memory_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "memory_id": row["memory_id"],
            "session_id": row["session_id"],
            "scope": row["scope"],
            "kind": row["kind"],
            "content": row["content"],
            "source": row["source"],
            "importance": row["importance"],
            "access_count": row["access_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_accessed_at": row["last_accessed_at"],
        }

    @_locked
    def health_check(self) -> bool:
        conn = self.connect()
        row = conn.execute("SELECT 1 AS ok").fetchone()
        return row is not None and row["ok"] == 1

    def _document_access_clause(
        self,
        *,
        owner_id: str | None,
        include_global: bool = True,
        alias: str = "",
    ) -> tuple[str, list[Any]]:
        if owner_id is None:
            return "", []

        prefix = f"{alias}." if alias else ""
        clauses: list[str] = []
        params: list[Any] = []
        if include_global:
            clauses.append(f"{prefix}visibility = 'global'")
        clauses.append(f"{prefix}owner_id = ?")
        params.append(normalize_document_owner_id(owner_id))
        return f"({' OR '.join(clauses)})", params

    def _document_ids_clause(
        self,
        doc_ids: list[str] | tuple[str, ...] | set[str] | None,
        *,
        alias: str = "",
    ) -> tuple[str, list[Any]]:
        if doc_ids is None:
            return "", []

        normalized_doc_ids = [
            doc_id
            for doc_id in dict.fromkeys(str(raw_doc_id).strip() for raw_doc_id in doc_ids)
            if doc_id
        ]
        if not normalized_doc_ids:
            return "0 = 1", []

        prefix = f"{alias}." if alias else ""
        placeholders = ", ".join("?" for _ in normalized_doc_ids)
        return f"{prefix}doc_id IN ({placeholders})", normalized_doc_ids

    @_locked
    def upsert_document(
        self,
        doc_id: str,
        source_path: str,
        title: str,
        page_count: int,
        checksum: str,
        *,
        parser_version: str = "",
        chunking_version: str = "",
        embedding_model: str = "",
        chunk_size: int = 0,
        chunk_overlap: int = 0,
        chunk_count: int = 0,
        ingestion_status: str = "indexed",
        last_ingest_error: str = "",
        owner_id: str = "global",
        visibility: str = "global",
    ) -> None:
        conn = self.connect()
        normalized_owner_id = normalize_document_owner_id(owner_id)
        normalized_visibility = normalize_document_visibility(visibility)
        conn.execute(
            """
            INSERT INTO documents (
                doc_id, source_path, title, page_count, checksum,
                owner_id, visibility, ingestion_status, parser_version, chunking_version, embedding_model,
                chunk_size, chunk_overlap, chunk_count, ingest_started_at,
                ingest_completed_at, last_ingest_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                source_path = excluded.source_path,
                title = excluded.title,
                page_count = excluded.page_count,
                checksum = excluded.checksum,
                owner_id = excluded.owner_id,
                visibility = excluded.visibility,
                ingestion_status = excluded.ingestion_status,
                parser_version = excluded.parser_version,
                chunking_version = excluded.chunking_version,
                embedding_model = excluded.embedding_model,
                chunk_size = excluded.chunk_size,
                chunk_overlap = excluded.chunk_overlap,
                chunk_count = excluded.chunk_count,
                ingest_completed_at = CURRENT_TIMESTAMP,
                last_ingest_error = excluded.last_ingest_error,
                indexed_at = CURRENT_TIMESTAMP
            ON CONFLICT(source_path) DO UPDATE SET
                doc_id = excluded.doc_id,
                title = excluded.title,
                page_count = excluded.page_count,
                checksum = excluded.checksum,
                owner_id = excluded.owner_id,
                visibility = excluded.visibility,
                ingestion_status = excluded.ingestion_status,
                parser_version = excluded.parser_version,
                chunking_version = excluded.chunking_version,
                embedding_model = excluded.embedding_model,
                chunk_size = excluded.chunk_size,
                chunk_overlap = excluded.chunk_overlap,
                chunk_count = excluded.chunk_count,
                ingest_completed_at = CURRENT_TIMESTAMP,
                last_ingest_error = excluded.last_ingest_error,
                indexed_at = CURRENT_TIMESTAMP
            """,
            (
                doc_id,
                source_path,
                title,
                page_count,
                checksum,
                normalized_owner_id,
                normalized_visibility,
                ingestion_status,
                parser_version,
                chunking_version,
                embedding_model,
                int(chunk_size),
                int(chunk_overlap),
                int(chunk_count),
                last_ingest_error,
            )

        )
        conn.commit()

    @_locked
    def get_document_by_source_path(self, source_path: str) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute(
            """
            SELECT
                doc_id, source_path, title, page_count, checksum, indexed_at,
                owner_id, visibility,
                ingestion_status, parser_version, chunking_version, embedding_model,
                chunk_size, chunk_overlap, chunk_count, ingest_started_at,
                ingest_completed_at, last_ingest_error
            FROM documents
            WHERE source_path = ?
            """,
            (source_path,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    @_locked
    def record_document_ingestion_started(
        self,
        *,
        source_path: str,
        parser_version: str,
        chunking_version: str,
        embedding_model: str,
        chunk_size: int,
        chunk_overlap: int,
        owner_id: str = "global",
        visibility: str = "global",
    ) -> None:
        conn = self.connect()
        normalized_owner_id = normalize_document_owner_id(owner_id)
        normalized_visibility = normalize_document_visibility(visibility)
        conn.execute(
            """
            INSERT INTO document_ingestion_status (
                source_path, status, parser_version, chunking_version,
                embedding_model, chunk_size, chunk_overlap, owner_id, visibility,
                started_at, error
            )
            VALUES (?, 'running', ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, '')
            ON CONFLICT(source_path) DO UPDATE SET
                status = 'running',
                parser_version = excluded.parser_version,
                chunking_version = excluded.chunking_version,
                embedding_model = excluded.embedding_model,
                chunk_size = excluded.chunk_size,
                chunk_overlap = excluded.chunk_overlap,
                owner_id = excluded.owner_id,
                visibility = excluded.visibility,
                started_at = CURRENT_TIMESTAMP,
                completed_at = NULL,
                error = ''
            """,
            (
                source_path,
                parser_version,
                chunking_version,
                embedding_model,
                int(chunk_size),
                int(chunk_overlap),
                normalized_owner_id,
                normalized_visibility,
            ),
        )
        conn.commit()

    @_locked
    def record_document_ingestion_completed(
        self,
        *,
        source_path: str,
        doc_id: str,
        title: str,
        status: str,
        checksum: str,
        page_count: int,
        chunk_count: int,
        parser_version: str,
        chunking_version: str,
        embedding_model: str,
        chunk_size: int,
        chunk_overlap: int,
        owner_id: str = "global",
        visibility: str = "global",
    ) -> None:
        conn = self.connect()
        normalized_owner_id = normalize_document_owner_id(owner_id)
        normalized_visibility = normalize_document_visibility(visibility)
        conn.execute(
            """
            INSERT INTO document_ingestion_status (
                source_path, doc_id, title, status, parser_version, chunking_version,
                embedding_model, chunk_size, chunk_overlap, checksum, page_count,
                chunk_count, owner_id, visibility, started_at, completed_at, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '')
            ON CONFLICT(source_path) DO UPDATE SET
                doc_id = excluded.doc_id,
                title = excluded.title,
                status = excluded.status,
                parser_version = excluded.parser_version,
                chunking_version = excluded.chunking_version,
                embedding_model = excluded.embedding_model,
                chunk_size = excluded.chunk_size,
                chunk_overlap = excluded.chunk_overlap,
                checksum = excluded.checksum,
                page_count = excluded.page_count,
                chunk_count = excluded.chunk_count,
                owner_id = excluded.owner_id,
                visibility = excluded.visibility,
                completed_at = CURRENT_TIMESTAMP,
                error = ''
            """,
            (
                source_path,
                doc_id,
                title,
                status,
                parser_version,
                chunking_version,
                embedding_model,
                int(chunk_size),
                int(chunk_overlap),
                checksum,
                int(page_count),
                int(chunk_count),
                normalized_owner_id,
                normalized_visibility,
            ),
        )
        conn.commit()

    @_locked
    def record_document_ingestion_failed(
        self,
        *,
        source_path: str,
        error: str,
        parser_version: str,
        chunking_version: str,
        embedding_model: str,
        chunk_size: int,
        chunk_overlap: int,
        owner_id: str = "global",
        visibility: str = "global",
    ) -> None:
        conn = self.connect()
        truncated_error = " ".join((error or "").split())[:2000]
        normalized_owner_id = normalize_document_owner_id(owner_id)
        normalized_visibility = normalize_document_visibility(visibility)
        conn.execute(
            """
            INSERT INTO document_ingestion_status (
                source_path, status, parser_version, chunking_version,
                embedding_model, chunk_size, chunk_overlap, started_at,
                completed_at, error, owner_id, visibility
            )
            VALUES (?, 'failed', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?, ?)
            ON CONFLICT(source_path) DO UPDATE SET
                status = 'failed',
                parser_version = excluded.parser_version,
                chunking_version = excluded.chunking_version,
                embedding_model = excluded.embedding_model,
                chunk_size = excluded.chunk_size,
                chunk_overlap = excluded.chunk_overlap,
                completed_at = CURRENT_TIMESTAMP,
                error = excluded.error,
                owner_id = excluded.owner_id,
                visibility = excluded.visibility
            """,
            (
                source_path,
                parser_version,
                chunking_version,
                embedding_model,
                int(chunk_size),
                int(chunk_overlap),
                truncated_error,
                normalized_owner_id,
                normalized_visibility,
            ),
        )
        conn.commit()

    @_locked
    def list_document_ingestion_status(
        self,
        limit: int = 50,
        *,
        status: str | None = None,
        owner_id: str | None = None,
        include_global: bool = True,
    ) -> list[dict[str, Any]]:
        conn = self.connect()
        bounded_limit = max(1, min(int(limit), 200))
        normalized_status = (status or "").strip()
        conditions: list[str] = []
        params: list[Any] = []
        if normalized_status:
            conditions.append("status = ?")
            params.append(normalized_status)
        access_clause, access_params = self._document_access_clause(
            owner_id=owner_id,
            include_global=include_global,
        )
        if access_clause:
            conditions.append(access_clause)
            params.extend(access_params)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(bounded_limit)
        rows = conn.execute(
            f"""
            SELECT source_path, doc_id, title, status, owner_id, visibility,
                   parser_version, chunking_version,
                   embedding_model, chunk_size, chunk_overlap, checksum, page_count,
                   chunk_count, started_at, completed_at, error
            FROM document_ingestion_status
            {where_sql}
            ORDER BY COALESCE(completed_at, started_at) DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    @_locked
    def get_document_ingestion_status_summary(
        self,
        *,
        owner_id: str | None = None,
        include_global: bool = True,
    ) -> dict[str, int]:
        conn = self.connect()
        access_clause, access_params = self._document_access_clause(
            owner_id=owner_id,
            include_global=include_global,
        )
        where_sql = f"WHERE {access_clause}" if access_clause else ""
        rows = conn.execute(
            f"""
            SELECT status, COUNT(*) AS count
            FROM document_ingestion_status
            {where_sql}
            GROUP BY status
            """,
            access_params,
        ).fetchall()
        counts = {str(row["status"] or ""): int(row["count"] or 0) for row in rows}
        total_count = sum(counts.values())
        return {
            "total_count": total_count,
            "running_count": counts.get("running", 0),
            "indexed_count": counts.get("indexed", 0),
            "skipped_count": counts.get("skipped", 0),
            "failed_count": counts.get("failed", 0),
        }

    @_locked
    def delete_chunks_for_doc(self, doc_id: str) -> None:
        conn = self.connect()
        conn.execute("DELETE FROM chunks WHERE doc_id = ?",(doc_id,))
        conn.commit()

    @_locked
    def insert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return
        conn = self.connect()
        conn.executemany(
            """
            INSERT INTO chunks (chunk_id, doc_id, chunk_index, page_number, text, token_estimate,section_title)
            VALUES (:chunk_id, :doc_id, :chunk_index, :page_number, :text, :token_estimate,:section_title)
            """,
            chunks,
        )
        conn.commit()

    @_locked
    def list_documents(
        self,
        *,
        search: str = "",
        limit: int | None = None,
        offset: int = 0,
        owner_id: str | None = None,
        include_global: bool = True,
        doc_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> list[dict[str, Any]]:
        conn= self.connect()
        normalized_search = search.strip()
        conditions: list[str] = []
        params: list[Any] = []
        if normalized_search:
            conditions.append(
                """
                (title LIKE ?
                 OR source_path LIKE ?
                 OR doc_id LIKE ?)
                """
            )
            pattern = f"%{normalized_search}%"
            params.extend([pattern, pattern, pattern])
        doc_id_clause, doc_id_params = self._document_ids_clause(doc_ids)
        if doc_id_clause:
            conditions.append(doc_id_clause)
            params.extend(doc_id_params)
        access_clause, access_params = self._document_access_clause(
            owner_id=owner_id,
            include_global=include_global,
        )
        if access_clause:
            conditions.append(access_clause)
            params.extend(access_params)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        limit_sql = ""
        if limit is not None:
            bounded_limit = max(1, min(int(limit), 100))
            bounded_offset = max(0, int(offset))
            limit_sql = "LIMIT ? OFFSET ?"
            params.extend([bounded_limit, bounded_offset])

        rows= conn.execute(
            f"""
            SELECT
                doc_id, source_path, title, page_count, checksum, indexed_at,
                owner_id, visibility,
                ingestion_status, parser_version, chunking_version, embedding_model,
                chunk_size, chunk_overlap, chunk_count, ingest_started_at,
                ingest_completed_at, last_ingest_error
            FROM documents
            {where_sql}
            ORDER BY indexed_at DESC
            {limit_sql}
            """,
            params,
        ).fetchall()

        return [
            {
                "doc_id": row["doc_id"],
                "source_path": row["source_path"],
                "title": row["title"],
                "page_count": row["page_count"],
                "checksum": row["checksum"],
                "indexed_at": row["indexed_at"],
                "owner_id": row["owner_id"],
                "visibility": row["visibility"],
                "ingestion_status": row["ingestion_status"],
                "parser_version": row["parser_version"],
                "chunking_version": row["chunking_version"],
                "embedding_model": row["embedding_model"],
                "chunk_size": row["chunk_size"],
                "chunk_overlap": row["chunk_overlap"],
                "chunk_count": row["chunk_count"],
                "ingest_started_at": row["ingest_started_at"],
                "ingest_completed_at": row["ingest_completed_at"],
                "last_ingest_error": row["last_ingest_error"],
            }
            for row in rows
        ]

    @_locked
    def insert_trace(self,
                     session_id: str,   
                     query:str,
                     top_k: int,
                     retrieved_json: str,
                     final_answer:str,
                     steps_json: str = "[]",
                     tool_results_json: str = "[]",
                     verification_json: str = "{}",
                     ) -> int:
        conn = self.connect()
        cursor = conn.execute(
            """
            INSERT INTO traces (session_id, query, top_k , retrieved_json, final_answer, steps_json, tool_results_json, verification_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, query, top_k, retrieved_json, final_answer, steps_json, tool_results_json, verification_json)
        )
        conn.commit()
        return int(cursor.lastrowid)

    @_locked
    def get_trace(self, trace_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute(
            """
            SELECT trace_id, session_id, query, top_k, retrieved_json, final_answer,
                   steps_json, tool_results_json, verification_json, created_at
            FROM traces
            WHERE trace_id = ?
            """,
            (trace_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    @_locked
    def list_traces(
        self,
        limit: int = 20,
        *,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conn = self.connect()
        if session_id:
            rows = conn.execute(
                """
                SELECT trace_id, session_id, query, final_answer, verification_json, created_at
                FROM traces
                WHERE session_id = ?
                ORDER BY trace_id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT trace_id, session_id, query, final_answer, verification_json, created_at
                FROM traces
                ORDER BY trace_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    @_locked
    def list_trace_audit_rows(
        self,
        limit: int = 50,
        *,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conn = self.connect()
        bounded_limit = max(1, min(int(limit), 200))
        if session_id:
            rows = conn.execute(
                """
                SELECT trace_id, session_id, query, steps_json, tool_results_json, created_at
                FROM traces
                WHERE session_id = ?
                ORDER BY trace_id DESC
                LIMIT ?
                """,
                (session_id, bounded_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT trace_id, session_id, query, steps_json, tool_results_json, created_at
                FROM traces
                ORDER BY trace_id DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    @_locked
    def upsert_answer_feedback(
        self,
        *,
        trace_id: int,
        rating: str,
        issue_type: str | None = None,
        source: str = "web",
    ) -> dict[str, Any]:
        if rating not in {"like", "dislike"}:
            raise ValueError("rating must be 'like' or 'dislike'")

        normalized_issue_type = normalize_feedback_issue_type(issue_type)
        conn = self.connect()
        trace = conn.execute(
            """
            SELECT trace_id
            FROM traces
            WHERE trace_id = ?
            """,
            (trace_id,),
        ).fetchone()
        if trace is None:
            raise ValueError(f"trace {trace_id} does not exist")

        existing = conn.execute(
            """
            SELECT issue_type
            FROM answer_feedback
            WHERE trace_id = ?
            """,
            (trace_id,),
        ).fetchone()
        if rating == "like":
            stored_issue_type = ""
        elif issue_type is None and existing is not None:
            stored_issue_type = existing["issue_type"] or ""
        else:
            stored_issue_type = normalized_issue_type

        conn.execute(
            """
            INSERT INTO answer_feedback (trace_id, rating, issue_type, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(trace_id) DO UPDATE SET
                rating = excluded.rating,
                issue_type = excluded.issue_type,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            (trace_id, rating, stored_issue_type, source),
        )
        row = conn.execute(
            """
            SELECT feedback_id, trace_id, rating, issue_type, source, created_at, updated_at
            FROM answer_feedback
            WHERE trace_id = ?
            """,
            (trace_id,),
        ).fetchone()
        conn.commit()
        return dict(row)

    @_locked
    def get_answer_feedback_for_trace(self, trace_id: int) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute(
            """
            SELECT feedback_id, trace_id, rating, issue_type, source, created_at, updated_at
            FROM answer_feedback
            WHERE trace_id = ?
            """,
            (trace_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    @_locked
    def list_answer_feedback(
        self,
        *,
        rating: str | None = None,
        limit: int = 20,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if rating is not None and rating not in {"like", "dislike"}:
            raise ValueError("rating must be 'like' or 'dislike'")

        conn = self.connect()
        bounded_limit = max(1, min(limit, 100))
        if rating and session_id:
            rows = conn.execute(
                """
                SELECT
                    f.feedback_id,
                    f.trace_id,
                    f.rating,
                    f.issue_type,
                    f.source,
                    f.created_at,
                    f.updated_at,
                    t.query,
                    t.final_answer
                FROM answer_feedback f
                JOIN traces t ON t.trace_id = f.trace_id
                WHERE f.rating = ?
                  AND t.session_id = ?
                ORDER BY f.updated_at DESC, f.feedback_id DESC
                LIMIT ?
                """,
                (rating, session_id, bounded_limit),
            ).fetchall()
        elif rating:
            rows = conn.execute(
                """
                SELECT
                    f.feedback_id,
                    f.trace_id,
                    f.rating,
                    f.issue_type,
                    f.source,
                    f.created_at,
                    f.updated_at,
                    t.query,
                    t.final_answer
                FROM answer_feedback f
                JOIN traces t ON t.trace_id = f.trace_id
                WHERE f.rating = ?
                ORDER BY f.updated_at DESC, f.feedback_id DESC
                LIMIT ?
                """,
                (rating, bounded_limit),
            ).fetchall()
        elif session_id:
            rows = conn.execute(
                """
                SELECT
                    f.feedback_id,
                    f.trace_id,
                    f.rating,
                    f.issue_type,
                    f.source,
                    f.created_at,
                    f.updated_at,
                    t.query,
                    t.final_answer
                FROM answer_feedback f
                JOIN traces t ON t.trace_id = f.trace_id
                WHERE t.session_id = ?
                ORDER BY f.updated_at DESC, f.feedback_id DESC
                LIMIT ?
                """,
                (session_id, bounded_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    f.feedback_id,
                    f.trace_id,
                    f.rating,
                    f.issue_type,
                    f.source,
                    f.created_at,
                    f.updated_at,
                    t.query,
                    t.final_answer
                FROM answer_feedback f
                JOIN traces t ON t.trace_id = f.trace_id
                ORDER BY f.updated_at DESC, f.feedback_id DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    @_locked
    def get_answer_feedback_summary(
        self,
        *,
        recent_limit: int = 5,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        conn = self.connect()
        if session_id:
            summary = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_count,
                    COALESCE(SUM(CASE WHEN f.rating = 'like' THEN 1 ELSE 0 END), 0) AS like_count,
                    COALESCE(SUM(CASE WHEN f.rating = 'dislike' THEN 1 ELSE 0 END), 0) AS dislike_count,
                    MAX(f.updated_at) AS latest_feedback_at
                FROM answer_feedback f
                JOIN traces t ON t.trace_id = f.trace_id
                WHERE t.session_id = ?
                """,
                (session_id,),
            ).fetchone()
            issue_rows = conn.execute(
                """
                SELECT f.issue_type, COUNT(*) AS count
                FROM answer_feedback f
                JOIN traces t ON t.trace_id = f.trace_id
                WHERE f.rating = 'dislike'
                  AND f.issue_type <> ''
                  AND t.session_id = ?
                GROUP BY f.issue_type
                ORDER BY count DESC, f.issue_type ASC
                """,
                (session_id,),
            ).fetchall()
        else:
            summary = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_count,
                    COALESCE(SUM(CASE WHEN rating = 'like' THEN 1 ELSE 0 END), 0) AS like_count,
                    COALESCE(SUM(CASE WHEN rating = 'dislike' THEN 1 ELSE 0 END), 0) AS dislike_count,
                    MAX(updated_at) AS latest_feedback_at
                FROM answer_feedback
                """
            ).fetchone()
            issue_rows = conn.execute(
                """
                SELECT issue_type, COUNT(*) AS count
                FROM answer_feedback
                WHERE rating = 'dislike'
                  AND issue_type <> ''
                GROUP BY issue_type
                ORDER BY count DESC, issue_type ASC
                """
            ).fetchall()
        total_count = int(summary["total_count"] or 0)
        dislike_count = int(summary["dislike_count"] or 0)
        dislike_rate = (dislike_count / total_count) if total_count else 0.0
        return {
            "total_count": total_count,
            "like_count": int(summary["like_count"] or 0),
            "dislike_count": dislike_count,
            "dislike_rate": dislike_rate,
            "issue_counts": {
                row["issue_type"]: int(row["count"] or 0)
                for row in issue_rows
            },
            "latest_feedback_at": summary["latest_feedback_at"] or "",
            "recent_dislikes": self.list_answer_feedback(
                rating="dislike",
                limit=max(1, min(recent_limit, 20)),
                session_id=session_id,
            ),
        }

    @_locked
    def list_chunks_for_retrieval(
        self,
        doc_id: str | None = None,
        *,
        candidate_doc_ids: list[str] | tuple[str, ...] | set[str] | None = None,
        owner_id: str | None = None,
        include_global: bool = True,
    ) -> list[dict]:
        conn = self.connect()
        conditions: list[str] = []
        params: list[Any] = []
        if doc_id:
            conditions.append("c.doc_id = ?")
            params.append(doc_id)
        doc_id_clause, doc_id_params = self._document_ids_clause(
            candidate_doc_ids,
            alias="c",
        )
        if doc_id_clause:
            conditions.append(doc_id_clause)
            params.extend(doc_id_params)
        access_clause, access_params = self._document_access_clause(
            owner_id=owner_id,
            include_global=include_global,
            alias="d",
        )
        if access_clause:
            conditions.append(access_clause)
            params.extend(access_params)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = conn.execute(
            f"""
            SELECT
                c.chunk_id,
                c.doc_id,
                c.chunk_index,
                c.page_number,
                c.text,
                c.token_estimate,
                c.section_title,
                d.title,
                d.source_path,
                d.owner_id,
                d.visibility
            FROM chunks c
            JOIN documents d
                ON c.doc_id = d.doc_id
            {where_sql}
            ORDER BY d.title, c.page_number, c.chunk_index
            """,
            params,
        ).fetchall()

        return [
            {
                "chunk_id":row["chunk_id"],
                "doc_id":row["doc_id"],
                "chunk_index":row["chunk_index"],
                "page_number":row["page_number"],
                "text":row["text"],
                "token_estimate":row["token_estimate"],
                "section_title":row["section_title"],
                "title":row["title"],
                "source_path":row["source_path"],
                "owner_id": row["owner_id"],
                "visibility": row["visibility"],
            }
            for row in rows
        ]

    @_locked
    def get_chunk_by_id(self, chunk_id: str) -> dict[str, Any] | None:
        conn = self.connect()
        row = conn.execute(
            """
            SELECT 
                c.chunk_id,
                c.doc_id,
                c.chunk_index,
                c.page_number,
                c.text, 
                c.token_estimate,
                c.section_title,
                d.title,
                d.source_path
            FROM chunks c
            JOIN documents d 
                ON c.doc_id = d.doc_id
            WHERE c.chunk_id = ?
            """,
            (chunk_id,)
        ).fetchone()

        if row is None:
            return None
        
        return self._chunk_row_to_dict(row)

    @_locked
    def get_neighbor_chunks(self, 
                            doc_id:str,
                            chunk_index:int,
                            window: int = 1,
                            ) -> list[dict[str,Any]]:

        """
        Return neighboring chunks from the same document only.

        This is multi-document safe because it filters by doc_id.
        Example: window=1 returns previous, current, next chunk.
        """
        conn = self.connect()
        start_index = max(0, chunk_index - window)
        end_index = chunk_index + window
        
        rows = conn.execute(
            """
            SELECT 
                c.chunk_id,
                c.doc_id,
                c.chunk_index,
                c.page_number,
                c.text, 
                c.token_estimate,
                c.section_title,
                d.title,
                d.source_path
            FROM chunks c
            JOIN documents d 
                ON c.doc_id = d.doc_id
            WHERE c.doc_id = ?
              AND c.chunk_index BETWEEN ? AND ?
            ORDER BY c.chunk_index
            """,
            (doc_id, start_index, end_index)
        ).fetchall()

        return [self._chunk_row_to_dict(row) for row in rows]

    def _chunk_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """
        Safe chunk row converter that handles missing columns gracefully.
        """
        return {
        "id":row["chunk_id"],    
        "chunk_id": row["chunk_id"],
        "doc_id": row["doc_id"],
        "chunk_index": row["chunk_index"],
        "page_number": row["page_number"],
        "text": row["text"],
        "token_estimate": row["token_estimate"],
        "section_title": row["section_title"] if "section_title" in row.keys() else None,
        "title": row["title"],
        "source_path": row["source_path"],
        "owner_id": row["owner_id"] if "owner_id" in row.keys() else "global",
        "visibility": row["visibility"] if "visibility" in row.keys() else "global",
    }
        
    @_locked
    def list_documents_for_routing(
        self,
        *,
        owner_id: str | None = None,
        include_global: bool = True,
        doc_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> list[dict[str, Any]]:
        conn=self.connect()
        conditions: list[str] = []
        params: list[Any] = []
        doc_id_clause, doc_id_params = self._document_ids_clause(doc_ids, alias="d")
        if doc_id_clause:
            conditions.append(doc_id_clause)
            params.extend(doc_id_params)
        access_clause, access_params = self._document_access_clause(
            owner_id=owner_id,
            include_global=include_global,
            alias="d",
        )
        if access_clause:
            conditions.append(access_clause)
            params.extend(access_params)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows=conn.execute(
            f"""
            SELECT
                d.doc_id,
                d.title,
                d.source_path,
                d.page_count,
                d.indexed_at,
                d.owner_id,
                d.visibility,
                COALESCE(GROUP_CONCAT(DISTINCT c.section_title), '') AS section_titles
            FROM documents d
            LEFT JOIN chunks c 
                ON d.doc_id = c.doc_id
            {where_sql}
            GROUP BY d.doc_id, d.title, d.source_path, d.page_count, d.indexed_at, d.owner_id, d.visibility
            ORDER BY d.indexed_at DESC;
            """,
            params,
        ).fetchall()
        return [
            {
                "doc_id": row["doc_id"],
                "title": row["title"],
                "source_path": row["source_path"],
                "page_count": row["page_count"],
                "indexed_at": row["indexed_at"],
                "owner_id": row["owner_id"],
                "visibility": row["visibility"],
                "section_titles": row["section_titles"] or "",
            }
            for row in rows
        ]

    @_locked
    def routing_corpus_signature(self) -> tuple[Any, ...]:
        conn = self.connect()
        row = conn.execute(
            """
            SELECT
                COUNT(DISTINCT d.doc_id) AS doc_count,
                COUNT(c.chunk_id) AS chunk_count,
                COALESCE(SUM(LENGTH(c.text)), 0) AS chunk_text_size,
                COALESCE(SUM(c.token_estimate), 0) AS token_estimate_total,
                COALESCE(MAX(d.indexed_at), '') AS latest_indexed_at,
                COALESCE(MAX(d.checksum), '') AS max_checksum
            FROM documents d
            LEFT JOIN chunks c
                ON d.doc_id = c.doc_id
            """
        ).fetchone()
        return (
            "routing_v1",
            int(row["doc_count"] or 0),
            int(row["chunk_count"] or 0),
            int(row["chunk_text_size"] or 0),
            int(row["token_estimate_total"] or 0),
            row["latest_indexed_at"] or "",
            row["max_checksum"] or "",
        )

    @_locked
    def accessible_document_ids(
        self,
        *,
        owner_id: str,
        include_global: bool = True,
    ) -> list[str]:
        conn = self.connect()
        access_clause, access_params = self._document_access_clause(
            owner_id=owner_id,
            include_global=include_global,
        )
        where_sql = f"WHERE {access_clause}" if access_clause else ""
        rows = conn.execute(
            f"""
            SELECT doc_id
            FROM documents
            {where_sql}
            ORDER BY indexed_at DESC
            """,
            access_params,
        ).fetchall()
        return [str(row["doc_id"]) for row in rows]

    @_locked
    def count_documents(
        self,
        *,
        search: str = "",
        owner_id: str | None = None,
        include_global: bool = True,
        doc_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> int:
        conn = self.connect()
        normalized_search = search.strip()
        conditions: list[str] = []
        params: list[Any] = []

        if normalized_search:
            pattern = f"%{normalized_search}%"
            conditions.append(
                """
                (title LIKE ?
                 OR source_path LIKE ?
                 OR doc_id LIKE ?)
                """
            )
            params.extend([pattern, pattern, pattern])
        doc_id_clause, doc_id_params = self._document_ids_clause(doc_ids)
        if doc_id_clause:
            conditions.append(doc_id_clause)
            params.extend(doc_id_params)
        access_clause, access_params = self._document_access_clause(
            owner_id=owner_id,
            include_global=include_global,
        )
        if access_clause:
            conditions.append(access_clause)
            params.extend(access_params)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM documents
            {where_sql}
            """,
            params,
        ).fetchone()
        return int(row["total"] or 0)

    @_locked
    def list_tables(self) -> list[dict[str, Any]]:
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        tables: list[dict[str, Any]] = []
        for row in rows:
            table_name = row["name"]
            count_row = conn.execute(
                f"SELECT COUNT(*) AS row_count FROM {_quote_identifier(table_name)}"
            ).fetchone()
            tables.append(
                {
                    "name": table_name,
                    "row_count": int(count_row["row_count"] or 0),
                }
            )
        return tables

    @_locked
    def preview_table(self, table_name: str, limit: int = 5) -> dict[str, Any]:
        normalized_table = (table_name or "").strip()
        allowed_tables = {table["name"] for table in self.list_tables()}
        if normalized_table not in allowed_tables:
            raise ValueError(f"Unknown table: {table_name}")

        bounded_limit = max(1, min(int(limit), 50))
        conn = self.connect()
        quoted_table = _quote_identifier(normalized_table)
        column_rows = conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
        columns = [row["name"] for row in column_rows]
        rows = conn.execute(
            f"SELECT * FROM {quoted_table} LIMIT ?",
            (bounded_limit,),
        ).fetchall()

        return {
            "table": normalized_table,
            "columns": columns,
            "limit": bounded_limit,
            "rows": [
                {key: _sqlite_value(row[key]) for key in row.keys()}
                for row in rows
            ],
        }

    @_locked
    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
