# App Package Structure

The `app` package is the application composition and interface layer.

It should stay small and should not become a mixed bucket for every feature.

## What Belongs In `app`

Keep these in `src/local_agent/app/`:

- `bootstrap.py`: creates and wires runtime dependencies.
- `config.py`: loads environment configuration.
- `dependencies.py`: dependency container.
- `paths.py`: project/runtime path registry.
- `main.py`: console entrypoint.
- `cli.py`: command-line interface.
- `web.py`: FastAPI routes and web entrypoint.
- `api_models.py`: request/response models for the web API.
- `tool_audit.py`: read-only audit projection from saved trace/tool steps.

These files are close to application startup, user interfaces, or runtime composition.

## What Was Moved Out

The following concerns now live outside `app`:

```text
src/local_agent/llm/
  ollama_client.py

src/local_agent/tools/
  tool_registry.py
  weather_tool.py
  file_mcp.py
  sqlite_mcp.py
  mcp_adapter.py

src/local_agent/evaluation/
  eval_candidates.py
  eval_runner.py

src/local_agent/operations/
  runtime_backup.py
```

The old mixed app modules were removed after internal imports were updated. New code should import from the new packages directly.

## Import Rules

Use these imports in new code:

```python
from local_agent.llm import OllamaChatClient, OllamaEmbeddingClient
from local_agent.tools import ToolRegistry, CurrentWeatherTool
from local_agent.evaluation.eval_runner import run_candidate_eval
from local_agent.operations import backup_runtime_state, restore_runtime_state
```

Avoid adding new business logic to `app`. If a file is not about startup, CLI, web API, configuration, or dependency wiring, it probably belongs in a domain package.

## Why This Matters

This separation makes the system easier to scale:

- `retrieval` finds evidence,
- `answering` synthesizes responses,
- `tools` owns guarded external/local capabilities,
- `llm` owns model-provider clients,
- `evaluation` owns quality scoring and eval drafts,
- `operations` owns operator workflows such as local backup and restore,
- `app` wires the product together.
