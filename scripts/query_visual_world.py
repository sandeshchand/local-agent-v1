from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def query_chunks(db_path: Path, output_path: Path) -> int:
    terms = ["visual world", "patch", "represent"]
    where_clause = " OR ".join("text LIKE ?" for _ in terms)
    parameters = [f"%{term}%" for term in terms]

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT page_number, chunk_index, text FROM chunks WHERE {where_clause}",
            parameters,
        )
        rows = cursor.fetchall()

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(f"Found {len(rows)} matching chunks.\n")
        for page_number, chunk_index, text in rows:
            handle.write(f"Page {page_number} Chunk {chunk_index}:\n{text}\n{'-' * 40}\n")

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug query for inspecting matching SQLite chunks.")
    parser.add_argument("--db", default="var/sqlite/app.db", help="Path to local SQLite app database.")
    parser.add_argument("--output", default="query_results.txt", help="Output text file.")
    args = parser.parse_args()

    count = query_chunks(Path(args.db), Path(args.output))
    print(f"Wrote {count} matching chunks to {args.output}")


if __name__ == "__main__":
    main()
