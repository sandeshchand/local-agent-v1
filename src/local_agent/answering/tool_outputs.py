from __future__ import annotations

import json


class ToolOutputMixin:
    def _answer_from_structured_tool_output(self, tool_context: str) -> str:
        try:
            payload = json.loads(tool_context)
        except (TypeError, json.JSONDecodeError):
            return ""

        if not isinstance(payload, dict):
            return ""

        if payload.get("tool") == "get_current_weather":
            return self._format_weather_tool_answer(payload)
        if payload.get("source") == "mcp":
            return self._format_mcp_tool_answer(payload)

        return ""
    def _format_weather_tool_answer(self, payload: dict) -> str:
        location = payload.get("location") or "the requested location"
        temperature = payload.get("temperature")
        apparent_temperature = payload.get("apparent_temperature")
        condition = payload.get("condition")
        time = payload.get("time")
        timezone = payload.get("timezone")

        if not temperature:
            return "The weather tool did not return a current temperature."

        answer = f"The current temperature in {location} is {temperature}"
        if apparent_temperature:
            answer += f", with an apparent temperature of {apparent_temperature}"
        if condition:
            answer += f". Conditions: {condition}."
        else:
            answer += "."
        if time:
            answer += f" Reported at {time}"
            if timezone:
                answer += f" ({timezone})"
            answer += "."
        return answer
    def _format_mcp_tool_answer(self, payload: dict) -> str:
        result = payload.get("result")
        if not isinstance(result, dict):
            return ""

        tool = result.get("tool") or payload.get("tool_name") or "mcp_tool"
        if result.get("success") is False:
            error = result.get("error") or "The tool could not complete the request."
            return f"The MCP tool could not complete the request: {error}"

        if tool == "list_tables":
            tables = result.get("tables") or []
            if not tables:
                return "No SQLite tables were found."
            lines = [
                f"- {table.get('name')} ({table.get('row_count', 0)} rows)"
                for table in tables
            ]
            return "SQLite tables:\n" + "\n".join(lines)

        if tool == "preview_table":
            table = result.get("table") or "the requested table"
            rows = result.get("rows") or []
            columns = result.get("columns") or []
            if not rows:
                column_text = ", ".join(columns) if columns else "no columns"
                return f"Table {table} has no rows. Columns: {column_text}."

            lines = []
            for index, row in enumerate(rows[:10], start=1):
                if isinstance(row, dict):
                    values = "; ".join(
                        f"{key}={self._short_tool_value(value)}"
                        for key, value in row.items()
                    )
                else:
                    values = self._short_tool_value(row)
                lines.append(f"{index}. {values}")
            return f"Preview of SQLite table {table}:\n" + "\n".join(lines)

        if tool == "recent_traces":
            traces = result.get("traces") or []
            if not traces:
                return "No recent traces were found in SQLite."
            lines = []
            for trace in traces[:20]:
                if not isinstance(trace, dict):
                    continue
                trace_id = trace.get("trace_id")
                status = ""
                verification = trace.get("verification_json")
                if isinstance(verification, str) and verification:
                    try:
                        status = json.loads(verification).get("status") or ""
                    except json.JSONDecodeError:
                        status = ""
                query = self._short_tool_value(trace.get("query") or "")
                lines.append(f"- Trace {trace_id}: {status or 'no verifier'} - {query}")
            return "Recent SQLite traces:\n" + "\n".join(lines)

        if tool == "feedback_summary":
            total = result.get("total_count", 0)
            likes = result.get("like_count", 0)
            dislikes = result.get("dislike_count", 0)
            rate = float(result.get("dislike_rate") or 0.0)
            answer = (
                f"Feedback summary: {total} total, {likes} liked, "
                f"{dislikes} disliked, dislike rate {rate:.0%}."
            )
            issue_counts = result.get("issue_counts") or {}
            if issue_counts:
                issue_text = ", ".join(
                    f"{issue}: {count}"
                    for issue, count in issue_counts.items()
                )
                answer += f" Issue counts: {issue_text}."
            return answer

        if tool == "list_directory":
            entries = result.get("entries") or []
            if not entries:
                return f"No entries were found in {result.get('path') or 'the requested location'}."
            names = []
            for entry in entries[:30]:
                entry_type = entry.get("type") or "item"
                entry_path = entry.get("path") or entry.get("name") or ""
                names.append(f"- {entry_path} ({entry_type})")
            answer = f"Files in {result.get('path') or 'the allowed File MCP roots'}:\n" + "\n".join(names)
            if result.get("truncated"):
                answer += "\nThe list was truncated."
            return answer

        if tool == "read_text_file":
            path = result.get("path") or "the requested file"
            content = str(result.get("content") or "")
            if result.get("truncated"):
                return f"Here is the beginning of {path}:\n\n{content}\n\nThe file was truncated."
            return f"Here is the content of {path}:\n\n{content}"

        if tool == "file_info":
            path = result.get("path") or "the requested path"
            kind = "directory" if result.get("is_dir") else "file"
            size = result.get("size_bytes")
            modified = result.get("modified_at")
            answer = f"{path} is a {kind}."
            if size is not None:
                answer += f" Size: {size} bytes."
            if modified:
                answer += f" Modified: {modified}."
            return answer

        return ""
    def _short_tool_value(self, value: object, max_length: int = 120) -> str:
        text = str(value).replace("\n", " ").strip()
        if len(text) <= max_length:
            return text
        return f"{text[: max_length - 3]}..."
