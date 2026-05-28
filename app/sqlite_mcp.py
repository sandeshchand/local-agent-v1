from __future__ import annotations

from typing import Any

from storage.sqlite_store import SQLiteStore


class ReadOnlySQLiteMCPClient:
    """Read-only SQLite inspection tools for local debugging."""

    def __init__(self, sqlite_store: SQLiteStore, *, default_limit: int = 10) -> None:
        self.sqlite_store = sqlite_store
        self.default_limit = max(1, min(default_limit, 50))

    def list_tools(self) -> dict[str, list[dict[str, Any]]]:
        read_only = {"readOnlyHint": True}
        return {
            "tools": [
                {
                    "name": "list_tables",
                    "description": "List local SQLite database tables and row counts.",
                    "inputSchema": {"type": "object", "properties": {}},
                    "annotations": read_only,
                },
                {
                    "name": "preview_table",
                    "description": "Preview rows from a local SQLite database table.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "table": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                        "required": ["table"],
                    },
                    "annotations": read_only,
                },
                {
                    "name": "recent_traces",
                    "description": "Show recent trace records from the local SQLite database.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"limit": {"type": "integer"}},
                    },
                    "annotations": read_only,
                },
                {
                    "name": "feedback_summary",
                    "description": "Show aggregate answer feedback from the local SQLite database.",
                    "inputSchema": {"type": "object", "properties": {}},
                    "annotations": read_only,
                },
            ]
        }

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "list_tables":
                return {
                    "tool": "list_tables",
                    "success": True,
                    "tables": self.sqlite_store.list_tables(),
                }
            if name == "preview_table":
                table = str(arguments.get("table") or "")
                limit = _as_int(arguments.get("limit"), default=self.default_limit, upper=50)
                return {
                    "tool": "preview_table",
                    "success": True,
                    **self.sqlite_store.preview_table(table, limit=limit),
                }
            if name == "recent_traces":
                limit = _as_int(arguments.get("limit"), default=self.default_limit, upper=50)
                return {
                    "tool": "recent_traces",
                    "success": True,
                    "limit": limit,
                    "traces": self.sqlite_store.list_traces(limit=limit),
                }
            if name == "feedback_summary":
                return {
                    "tool": "feedback_summary",
                    "success": True,
                    **self.sqlite_store.get_answer_feedback_summary(),
                }
        except ValueError as exc:
            return {
                "tool": name,
                "success": False,
                "error": str(exc),
            }

        return {
            "tool": name,
            "success": False,
            "error": f"Unknown read-only SQLite tool '{name}'.",
        }


def _as_int(value: Any, *, default: int, upper: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, upper))
