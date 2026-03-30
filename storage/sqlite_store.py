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
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS traces (
                trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                top_k INTEGER NOT NULL,
                retrieved_json TEXT NOT NULL,
                final_answer TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.commit()

    def health_check(self) -> bool:
        conn = self.connect()
        row = conn.execute("SELECT 1 AS ok").fetchone()
        return row is not None and row["ok"] == 1

    def upsert_document(self,
                        doc_id:str,
                        source_path:str,
                        title:str,
                        page_count:int,
                        checksum:str,) ->str:
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
            INSERT INTO chunks (chunk_id, doc_id, chunk_index, page_number, text, token_estimate)
            VALUES (:chunk_id, :doc_id, :chunk_index, :page_number, :text, :token_estimate)
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
                     query:str,
                     top_k: int,
                     retrieved_json: str,
                     final_answer:str,
                     ) -> int:
        conn = self.connect()
        cursor = conn.execute(
            """
            INSERT INTO traces (query, top_k , retrieved_json, final_answer)
            VALUES (?, ?, ?, ?)
            """,
            (query, top_k, retrieved_json, final_answer)
        )
        conn.commit()
        return int(cursor.lastrowid)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
