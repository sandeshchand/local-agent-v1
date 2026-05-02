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
        
    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
