from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SQLiteStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(str(self.db_path))
            self._connection.row_factory = sqlite3.Row
        return self._connection

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
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
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
                source TEXT NOT NULL DEFAULT 'web',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
            )
            """
        )

        conn.commit()
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

    def health_check(self) -> bool:
        conn = self.connect()
        row = conn.execute("SELECT 1 AS ok").fetchone()
        return row is not None and row["ok"] == 1

    def upsert_document(self,
                        doc_id:str,
                        source_path:str,
                        title:str,
                        page_count:int,
                        checksum:str,) ->None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO documents (doc_id, source_path, title, page_count, checksum)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                source_path = excluded.source_path,
                title = excluded.title,
                page_count = excluded.page_count,
                checksum = excluded.checksum,
                indexed_at = CURRENT_TIMESTAMP
            """,
            (doc_id, source_path, title, page_count, checksum)

        )
        conn.commit()

    def delete_chunks_for_doc(self, doc_id: str) -> None:
        conn = self.connect()
        conn.execute("DELETE FROM chunks WHERE doc_id = ?",(doc_id,))
        conn.commit()

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

    def list_documents(self) -> list[dict[str, Any]]:
        conn= self.connect()
        rows= conn.execute(
            """
            SELECT doc_id, source_path, title, page_count, checksum, indexed_at
            FROM documents
            ORDER BY indexed_at DESC
            """
        ).fetchall()

        return [
            {
                "doc_id": row["doc_id"],
                "source_path": row["source_path"],
                "title": row["title"],
                "page_count": row["page_count"],
                "checksum": row["checksum"],
                "indexed_at": row["indexed_at"],
            }
            for row in rows
        ]

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

    def list_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        conn = self.connect()
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

    def upsert_answer_feedback(
        self,
        *,
        trace_id: int,
        rating: str,
        source: str = "web",
    ) -> dict[str, Any]:
        if rating not in {"like", "dislike"}:
            raise ValueError("rating must be 'like' or 'dislike'")

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

        conn.execute(
            """
            INSERT INTO answer_feedback (trace_id, rating, source)
            VALUES (?, ?, ?)
            ON CONFLICT(trace_id) DO UPDATE SET
                rating = excluded.rating,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            (trace_id, rating, source),
        )
        row = conn.execute(
            """
            SELECT feedback_id, trace_id, rating, source, created_at, updated_at
            FROM answer_feedback
            WHERE trace_id = ?
            """,
            (trace_id,),
        ).fetchone()
        conn.commit()
        return dict(row)

    def list_chunks_for_retrieval(self,doc_id:str | None=None) -> list[dict]:
        conn = self.connect()
        if doc_id:
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
                ORDER BY d.title, c.page_number, c.chunk_index
                """,
                (doc_id,)
            ).fetchall()
        else:
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
                ORDER BY d.title, c.page_number, c.chunk_index
                """
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
            }
            for row in rows
        ]

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
    }
        
    def list_documents_for_routing(self) -> list[dict[str, Any]]:
        conn=self.connect()
        rows=conn.execute(
            """
            SELECT
                d.doc_id,
                d.title,
                d.source_path,
                d.page_count,
                d.indexed_at,
                COALESCE(GROUP_CONCAT(DISTINCT c.section_title), '') AS section_titles
            FROM documents d
            LEFT JOIN chunks c 
                ON d.doc_id = c.doc_id
            GROUP BY d.doc_id, d.title, d.source_path, d.page_count, d.indexed_at
            ORDER BY d.indexed_at DESC;
            """
        ).fetchall()
        return [
            {
                "doc_id": row["doc_id"],
                "title": row["title"],
                "source_path": row["source_path"],
                "page_count": row["page_count"],
                "indexed_at": row["indexed_at"],
                "section_titles": row["section_titles"] or "",
            }
            for row in rows
        ]

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
