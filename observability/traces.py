from __future__ import annotations

import json

from storage.sqlite_store import SQLiteStore

def save_trace(
        sqlite_store: SQLiteStore,
        query:str,
        top_k: int,
        retrieved_items: list[dict],
        final_answer: str,
        plan:dict | None = None
    ) ->int:
    payload = {
        "plan": plan or {},
        "retrieved_items": retrieved_items
    }
    return sqlite_store.insert_trace(
        query=query,
        top_k= top_k,
        retrieved_json=json.dumps(payload, ensure_ascii=False, indent=2),
        final_answer=final_answer,
    )