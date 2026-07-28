# Qdrant Server Mode Planning

The app currently uses Qdrant local path mode.

That is good for local development because it is simple and does not require a separate service. The tradeoff is that only one process should own the Qdrant path at a time. If the web UI is running, another CLI script may fail when it tries to open the same Qdrant path.

## When To Keep Local Path Mode

Keep local path mode when:

- one developer is running one local app process,
- the corpus is still small,
- demos do not need multiple web workers,
- deployment is not yet multi-user.

As a practical rule, local path mode is still fine below about `100` documents and `10,000` chunks.

## When To Test Server Mode

Start testing server mode when:

- the corpus grows beyond about `100` documents or `10,000` chunks,
- multiple users or workers need access,
- CLI profiling and the web UI need to run at the same time,
- retrieval-search p95 starts growing even after caches are warm.

Server mode becomes high priority around `1,000` documents or `50,000` chunks.

## Current Diagnostic

Run:

```powershell
venv\Scripts\python.exe scripts\profile_retrieval_scale.py --env-file .env --profile multi-doc-representative --warmup-retrieval --repeat-search 2 --output var\logs\retrieval_scale_profile.json
```

Read:

- `corpus.document_count`,
- `corpus.chunk_count`,
- `routing.average_cold_ms`,
- `routing.average_warm_ms`,
- `embedding_cache.average_cold_ms`,
- `embedding_cache.average_warm_ms`,
- `retrieval_search.p95_ms`,
- `recommendations`.

## Future Migration Shape

The production migration should be done as a config change, not as a retrieval rewrite.

Expected work:

- add Qdrant URL/API-key config,
- update `QdrantStore` to support either local path mode or server URL mode,
- keep the same `RetrievalService.search()` interface,
- add a smoke test for both connection modes,
- document local-dev and production examples in `.env.example`.

Until this is implemented, keep only one local app process open when using the Qdrant path.
