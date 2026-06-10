# Memory Implementation

This document explains the memory layer in the local agentic RAG system.

The goal is not to make memory another source of document facts. PDF answers must still come from retrieved evidence. Memory is used for user preferences, project rules, task status, evaluation results, and known issues.

## What Was Implemented

## 1. Short-Term Memory

File: `src/local_agent/agent/memory_manager.py`

Short-term memory is the recent conversation history for the active `session_id`.

It is stored in:

```text
conversation_turns
```

It is used to keep local chat continuity, such as what the user just asked or what the assistant just answered.

Important methods:

```python
load_session_memory(session_id)
save_user_turn(session_id, content)
save_assistant_turn(session_id, content)
```

The old misspelled method `load_sesssion_memory()` is still available as an alias so older code does not break.

## 2. Long-Term Memory

File: `src/local_agent/storage/sqlite_store.py`

Long-term memory is stored in a new SQLite table:

```text
memory_items
```

Fields:

- `memory_id`: unique id
- `session_id`: session id for session-scoped memory
- `scope`: `global` or `session`
- `kind`: memory category
- `content`: short memory text
- `source`: `manual` or `auto`
- `importance`: ranking weight from `1.0` to `3.0`
- `access_count`: how often the memory was retrieved
- `created_at`, `updated_at`, `last_accessed_at`

Supported memory kinds:

```text
user_preference
project_decision
task_status
evaluation_result
known_issue
```

## 3. Memory Capture

File: `src/local_agent/agent/memory_manager.py`

The agent automatically captures only explicit memory-like messages, for example:

```text
Keep in mind we should not use document-specific hardcoded keywords.
Remember the eval benchmark must pass before commit.
Next step is to improve memory.
```

It does not capture every message. This prevents memory pollution.

The auto-capture method is:

```python
capture_long_term_memory(session_id, user_message)
```

## 4. Memory Guardrails

File: `src/local_agent/agent/memory_manager.py`

The memory layer rejects text that looks sensitive, including:

- passwords
- secrets
- API keys
- tokens
- private keys
- email addresses
- phone-number-like strings
- long hex secrets

This is handled by:

```python
_is_sensitive(text)
```

## 5. Relevant Memory Retrieval

File: `src/local_agent/agent/memory_manager.py`

The system does not inject all memories into every prompt.

It ranks memory items using:

- query/content token overlap
- important phrase matches
- memory kind
- importance score
- task-specific query hints such as `eval`, `benchmark`, `next`, `quality`, `RAG`, `agent`

Main method:

```python
load_relevant_memory(session_id, query)
```

Combined memory for a query:

```python
load_memory_for_query(session_id, query)
```

This returns:

1. relevant long-term memory
2. recent short-term conversation

## 6. Orchestrator Integration

File: `src/local_agent/agent/orchestrator.py`

The orchestration flow now does this at the beginning of every query:

```text
save user turn
-> capture explicit long-term memory
-> load relevant memory for current query
-> plan
-> route/retrieve/tool/direct answer
```

The trace steps now include a memory step:

```json
{
  "step": 0,
  "type": "memory",
  "captured_count": 1,
  "loaded_count": 4,
  "loaded_kinds": ["project_decision", "short_term"]
}
```

## 7. Prompt Integration

File: `src/local_agent/answering/prompts.py`

Memory is passed into retrieval, direct-answer, and tool-answer prompts.

For RAG answers, the prompt explicitly says:

```text
Use memory only for user preferences and project/process constraints.
Do not use memory as document evidence.
```

This protects answer grounding. If a PDF question asks for facts, those facts must still come from retrieved chunks and citations.

## 8. CLI Commands

File: `src/local_agent/app/cli.py`

Manually add a memory:

```cmd
local-agent remember --content "Do not use document-specific hardcoded keywords." --kind project_decision --importance 3
```

List memory:

```cmd
local-agent list-memory
```

Session-scoped memory:

```cmd
local-agent remember --content "Use short answers in this session." --kind user_preference --scope session --session-id default
```

## 9. Smoke Test

File: `scripts/smoke_memory.py`

Run:

```cmd
venv\Scripts\python.exe scripts\smoke_memory.py
```

It verifies:

- manual memory insert works
- automatic memory capture works
- sensitive-looking API key text is not stored
- relevant memory retrieval returns the right project rules
- formatted memory context contains long-term memory

## Current Design Choice

This implementation uses local SQLite and lexical relevance ranking first.

That is intentional. It is deterministic, fast, inspectable, and does not add a new vector collection before the behavior is proven. A later version can add embedding-based semantic memory retrieval once the memory categories and evaluation tests are stable.

## Next Improvements

1. Add memory-specific eval tests for multi-turn behavior.
2. Add an optional vector index for semantic memory retrieval.
3. Add a small UI panel to inspect/delete memory items.
4. Add memory decay or archiving for stale task-status items.
5. Add per-project memory namespaces if the app is used across multiple projects.
