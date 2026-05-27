# MCP Integration

MCP V1 adds a generic adapter layer for MCP-style tools. It does not start a File MCP server yet and it does not grant file write/delete access.

## Current Scope

Implemented:

- `app/mcp_adapter.py`
- MCP-style tool discovery through a small client protocol
- registration into the existing `ToolRegistry`
- MCP tool metadata on `ToolSpec`
- approval-required-by-default behavior for MCP tools
- read-only MCP tool support through `readOnlyHint` or `read_only`
- `/api/tools` endpoint for registered tool visibility
- MCP adapter smoke test

Not implemented yet:

- actual stdio/SSE MCP server process management
- File MCP server wiring
- write/delete file tools
- broad web search MCP tools

## Design

The adapter expects a client with two methods:

```python
list_tools() -> Any
call_tool(name: str, arguments: dict) -> Any
```

Discovered tools are registered under names like:

```text
mcp.<server_name>.<tool_name>
```

Example:

```text
mcp.file_server.read_file
```

## Safety Rule

MCP tools default to:

```text
requires_approval=True
```

Read-only tools can be allowed without approval when their metadata says one of:

```text
annotations.readOnlyHint = true
read_only = true
readOnly = true
```

All MCP tools still pass through the existing guardrail policy before execution.

## Evidence Boundary

MCP output is tool context. It is not PDF citation evidence.

For PDF questions, answers should still be grounded in retrieved PDF chunks and citations.

## Tool Visibility

Registered tools can be inspected through:

```text
GET /api/tools
```

Each item includes:

- name
- description
- source
- requires_approval
- metadata

## Verification

Run:

```cmd
venv\Scripts\python.exe -m py_compile app\mcp_adapter.py agent\schemas.py agent\orchestrator.py app\web.py
venv\Scripts\python.exe scripts\smoke_mcp_adapter.py
```

Or run the local smoke suite:

```cmd
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```

## Next MCP Work

1. Add a concrete MCP client wrapper for a chosen transport.
2. Wire a read-only File MCP server first.
3. Add path allowlists before enabling file write/delete tools.
4. Add UI visibility for tool approval prompts.
