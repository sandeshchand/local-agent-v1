from __future__ import annotations

import json
import tempfile
from pathlib import Path

from local_agent.agent.schemas import ToolSpec
from local_agent.app.tool_audit import build_tool_audit, guardrail_risk, tool_category
from local_agent.storage.sqlite_store import SQLiteStore
from local_agent.tools import ToolRegistry


def insert_guarded_trace(
    store: SQLiteStore,
    *,
    query: str,
    tool_name: str,
    status: str,
    requires_approval: bool = False,
    approved: bool = False,
    executed: bool = False,
) -> int:
    steps = [
        {
            "step": 2,
            "type": "guardrail",
            "status": status,
            "reason": f"{status} smoke",
            "tool_name": tool_name,
            "requires_approval": requires_approval,
            "approved": approved,
            "policy_name": "tool_call_guardrails_v1",
            "duration_ms": 1.2,
        }
    ]
    tool_results = []
    if executed:
        steps.append(
            {
                "step": 2,
                "type": "tool_call",
                "tool_name": tool_name,
                "tool_source": "mcp" if tool_name.startswith("mcp.") else "local",
                "tool_metadata": {"server_name": "sqlite"} if "sqlite" in tool_name else {},
                "success": True,
            }
        )
        tool_results.append({"tool_name": tool_name, "success": True, "output": "ok"})

    return store.insert_trace(
        session_id="tool-audit-smoke",
        query=query,
        top_k=3,
        retrieved_json="{}",
        final_answer="tool audit smoke",
        steps_json=json.dumps(steps),
        tool_results_json=json.dumps(tool_results),
        verification_json=json.dumps({"status": "verified"}),
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SQLiteStore(Path(tmpdir) / "tool_audit.db")
        store.initialize()
        registry = ToolRegistry()
        registry.register(
            ToolSpec(
                name="get_current_weather",
                description="Weather",
                requires_approval=False,
            ),
            lambda: "ok",
        )
        registry.register(
            ToolSpec(
                name="mcp.sqlite.list_tables",
                description="SQLite tables",
                requires_approval=False,
                source="mcp",
                metadata={"server_name": "sqlite"},
            ),
            lambda: "ok",
        )

        insert_guarded_trace(
            store,
            query="weather",
            tool_name="get_current_weather",
            status="allow",
            executed=True,
        )
        insert_guarded_trace(
            store,
            query="approval",
            tool_name="mcp.file_server.write_file",
            status="needs_approval",
            requires_approval=True,
        )
        insert_guarded_trace(
            store,
            query="denied",
            tool_name="missing_tool",
            status="deny",
        )
        insert_guarded_trace(
            store,
            query="approved sqlite",
            tool_name="mcp.sqlite.list_tables",
            status="allow",
            requires_approval=True,
            approved=True,
            executed=True,
        )

        audit = build_tool_audit(store, registry, limit=10)
        summary = audit["summary"]
        items = audit["items"]

        assert summary["total_count"] == 4
        assert summary["allow_count"] == 2
        assert summary["deny_count"] == 1
        assert summary["needs_approval_count"] == 1
        assert summary["approved_count"] == 1
        assert summary["executed_count"] == 2
        assert summary["blocked_count"] == 2
        assert summary["high_risk_count"] == 2
        assert summary["medium_risk_count"] == 1
        assert summary["low_risk_count"] == 1
        assert summary["write_delete_count"] == 1
        assert summary["category_counts"]["write_file"] == 1
        assert summary["risk_counts"]["high"] == 2

        by_tool = {item["tool_name"]: item for item in items}
        assert by_tool["get_current_weather"]["tool_category"] == "web_read"
        assert by_tool["get_current_weather"]["risk_level"] == "low"
        assert by_tool["mcp.sqlite.list_tables"]["tool_category"] == "read_db"
        assert by_tool["mcp.sqlite.list_tables"]["risk_level"] == "medium"
        assert by_tool["mcp.file_server.write_file"]["tool_category"] == "write_file"
        assert by_tool["mcp.file_server.write_file"]["risk_level"] == "high"
        assert by_tool["mcp.file_server.write_file"]["blocked"] is True
        assert by_tool["missing_tool"]["executed"] is False
        assert by_tool["missing_tool"]["risk_level"] == "high"
        assert by_tool["missing_tool"]["blocked"] is True
        assert tool_category("mcp.local_files.read_text_file", source="mcp") == "read_file"
        assert guardrail_risk(
            status="needs_approval",
            tool_category="read_file",
            requires_approval=True,
            executed=False,
        )[0] == "medium"

        store.close()

    print("Tool audit smoke test passed.")


if __name__ == "__main__":
    main()
