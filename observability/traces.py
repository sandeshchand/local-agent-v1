from __future__ import annotations

import json

from storage.sqlite_store import SQLiteStore

def save_trace(
        sqlite_store: SQLiteStore,
        query:str,
        top_k: int,
        retrieved_items: list[dict],
        final_answer: str,
    ) ->int:
    return sqlite_store.insert_trace(
        query=query,
        top_k= top_k,
        retrieved_json=json.dumps(retrieved_items, ensure_ascii=False, indent=2),
        final_answer=final_answer,
    )