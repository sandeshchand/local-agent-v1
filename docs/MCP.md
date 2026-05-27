# MCP Integration

MCP V1 adds a generic adapter layer plus a read-only local File MCP-style connector. It does not grant file write/delete access.

## Current Scope

Implemented:

- `app/mcp_adapter.py`
- `app/file_mcp.py`
- MCP-style tool discovery through a small client protocol
- registration into the existing `ToolRegistry`
- MCP tool metadata on `ToolSpec`
- approval-required-by-default behavior for MCP tools
- read-only MCP tool support through `readOnlyHint` or `read_only`
- read-only local file tools for allowed roots
- `/api/tools` endpoint for registered tool visibility
- MCP adapter smoke test
- File MCP smoke test

Not implemented yet:

- actual stdio/SSE MCP server process management
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

The local read-only file connector registers:

```text
mcp.local_files.list_directory
mcp.local_files.read_text_file
mcp.local_files.file_info
```

## How To Use File MCP Tools

Start or restart the web app:

```powershell
.\scripts\start_web.ps1
```

Check registered tools:

```text
http://127.0.0.1:8000/api/tools
```

Example CLI questions:

```cmd
venv\Scripts\python.exe app\main.py ask --query "List files in docs"
venv\Scripts\python.exe app\main.py ask --query "Read file docs/MCP.md"
venv\Scripts\python.exe app\main.py ask --query "Show metadata for file docs/MCP.md"
```

Example chat UI questions:

```text
List files in docs
Read file docs/MCP.md
Show metadata for file docs/MCP.md
```

## File Roots

By default, File MCP can read only:

```text
data
docs
test
README.md
pyproject.toml
```

Override this in `.env`:

```text
FILE_MCP_ENABLED=true
FILE_MCP_ROOTS=data,docs,test,README.md,pyproject.toml
```

Do not add broad roots like `.` or your home directory unless you are comfortable exposing all readable files under that path to the local agent.

## Safety Rule

MCP tools default to:

```text
requires_approval=True
```

Read-only tools are allowed without approval when their metadata says one of:

```text
annotations.readOnlyHint = true
read_only = true
readOnly = true
```

All MCP tools still pass through the existing guardrail policy before execution. File MCP tools also enforce path allowlists.

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
venv\Scripts\python.exe -m py_compile app\mcp_adapter.py app\file_mcp.py agent\schemas.py agent\orchestrator.py app\web.py
venv\Scripts\python.exe scripts\smoke_mcp_adapter.py
venv\Scripts\python.exe scripts\smoke_file_mcp.py
```

Or run the local smoke suite:

```cmd
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```

## Next MCP Work

1. Add a concrete MCP client wrapper for a chosen transport.
2. Add UI visibility for registered tools.
3. Add UI approval prompts for approval-required tool calls.
4. Add stronger path policy before enabling file write/delete tools.
