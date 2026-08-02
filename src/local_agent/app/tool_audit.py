from __future__ import annotations

import json
from typing import Any

from local_agent.tools import ToolRegistry
from local_agent.storage.sqlite_store import SQLiteStore


def build_tool_audit(
    sqlite_store: SQLiteStore,
    tool_registry: ToolRegistry,
    *,
    limit: int = 50,
    session_id: str | None = None,
) -> dict[str, Any]:
    rows = sqlite_store.list_trace_audit_rows(limit=limit, session_id=session_id)
    events: list[dict[str, Any]] = []
    tool_specs = {tool.name: tool for tool in tool_registry.list_tools()}

    for row in rows:
        steps = _parse_json(row.get("steps_json"), [])
        tool_results = _parse_json(row.get("tool_results_json"), [])
        tool_steps = [
            step
            for step in steps
            if isinstance(step, dict) and step.get("type") == "tool_call"
        ]

        for step in steps:
            if not isinstance(step, dict) or step.get("type") != "guardrail":
                continue
            tool_name = str(step.get("tool_name") or "")
            matching_tool_step = _matching_tool_step(tool_steps, tool_name, step.get("step"))
            spec = tool_specs.get(tool_name)
            source = str(
                (matching_tool_step or {}).get("tool_source")
                or (spec.source if spec else "unknown")
            )
            metadata = (
                (matching_tool_step or {}).get("tool_metadata")
                or (spec.metadata if spec else {})
                or {}
            )
            category = tool_category(tool_name, source=source, metadata=metadata)
            risk_level, risk_reason = guardrail_risk(
                status=str(step.get("status") or "unknown"),
                tool_category=category,
                requires_approval=bool(step.get("requires_approval")),
                executed=matching_tool_step is not None,
            )
            events.append(
                {
                    "trace_id": int(row["trace_id"]),
                    "session_id": row.get("session_id") or "default",
                    "query": row.get("query") or "",
                    "created_at": str(row.get("created_at") or ""),
                    "tool_name": tool_name,
                    "tool_source": source,
                    "tool_category": category,
                    "status": step.get("status") or "unknown",
                    "reason": step.get("reason") or "",
                    "requires_approval": bool(step.get("requires_approval")),
                    "approved": bool(step.get("approved")),
                    "executed": matching_tool_step is not None,
                    "success": _tool_success(tool_results, tool_name, matching_tool_step),
                    "policy_name": step.get("policy_name") or "",
                    "duration_ms": float(step.get("duration_ms") or 0.0),
                    "risk_level": risk_level,
                    "risk_reason": risk_reason,
                    "blocked": _is_blocked(step, matching_tool_step),
                }
            )

    summary = {
        "total_count": len(events),
        "allow_count": sum(1 for event in events if event["status"] == "allow"),
        "deny_count": sum(1 for event in events if event["status"] == "deny"),
        "needs_approval_count": sum(1 for event in events if event["status"] == "needs_approval"),
        "approved_count": sum(1 for event in events if event["approved"]),
        "executed_count": sum(1 for event in events if event["executed"]),
        "blocked_count": sum(1 for event in events if event["blocked"]),
        "high_risk_count": sum(1 for event in events if event["risk_level"] == "high"),
        "medium_risk_count": sum(1 for event in events if event["risk_level"] == "medium"),
        "low_risk_count": sum(1 for event in events if event["risk_level"] == "low"),
        "write_delete_count": sum(
            1 for event in events if event["tool_category"] in {"write_file", "delete_file"}
        ),
        "category_counts": _count_by(events, "tool_category"),
        "risk_counts": _count_by(events, "risk_level"),
    }
    return {"summary": summary, "items": events}


def tool_category(
    tool_name: str,
    *,
    source: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    metadata = metadata or {}
    explicit_category = metadata.get("category")
    if explicit_category:
        return str(explicit_category)

    lower_name = tool_name.lower()
    server_name = str(metadata.get("server_name") or "").lower()

    if any(term in lower_name for term in ["delete", "remove", "unlink"]):
        return "delete_file"
    if any(term in lower_name for term in ["write", "save", "create", "update"]):
        return "write_file"
    if "weather" in lower_name:
        return "web_read"
    if "sqlite" in lower_name or lower_name == "list_documents" or server_name == "sqlite":
        return "read_db"
    if "file" in lower_name or "directory" in lower_name or server_name in {"local_files", "file_server"}:
        return "read_file"
    if source == "mcp":
        return "mcp_read"
    return "local_read"


def guardrail_risk(
    *,
    status: str,
    tool_category: str,
    requires_approval: bool,
    executed: bool,
) -> tuple[str, str]:
    normalized_status = status.lower()
    if tool_category in {"write_file", "delete_file"}:
        return "high", "Write/delete-capable tool category."
    if normalized_status == "deny":
        return "high", "Guardrails denied this tool action."
    if normalized_status == "needs_approval":
        return "medium", "Execution is blocked until request-scoped approval."
    if requires_approval:
        return "medium", "Tool requires explicit request approval."
    if executed and tool_category in {"read_file", "read_db", "mcp_read", "web_read"}:
        return "low", "Read-only tool execution."
    return "low", "Low-risk local/read-only tool decision."


def _is_blocked(step: dict[str, Any], matching_tool_step: dict[str, Any] | None) -> bool:
    status = str(step.get("status") or "").lower()
    return status in {"deny", "needs_approval"} and matching_tool_step is None


def _count_by(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(item.get(field) or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _parse_json(raw: Any, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(str(raw))
    except json.JSONDecodeError:
        return default


def _matching_tool_step(
    tool_steps: list[dict[str, Any]],
    tool_name: str,
    step_no: Any,
) -> dict[str, Any] | None:
    for step in tool_steps:
        if step.get("tool_name") == tool_name and step.get("step") == step_no:
            return step
    for step in tool_steps:
        if step.get("tool_name") == tool_name:
            return step
    return None


def _tool_success(
    tool_results: list[Any],
    tool_name: str,
    matching_tool_step: dict[str, Any] | None,
) -> bool | None:
    for result in tool_results:
        if not isinstance(result, dict):
            continue
        if result.get("tool_name") == tool_name:
            return bool(result.get("success"))
    if matching_tool_step is None:
        return None
    if "success" in matching_tool_step:
        return bool(matching_tool_step.get("success"))
    return None
