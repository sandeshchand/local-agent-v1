# Evaluation

This project uses repeatable local evaluation to check whether RAG changes improve answer quality without overfitting to one PDF.

## Evaluation Layers

There are three useful evaluation layers:

- RAG answer quality eval: checks the final answer, citations, routing, verifier status, and drift.
- Retrieval eval: checks whether retrieval returned the expected pages and keywords before answer generation.
- Memory eval: checks multi-turn memory retrieval, preference capture, task-status recall, and sensitive-text redaction.
- Regression runner: runs compile checks, smoke tests, and a focused RAG quality gate before commits.

## Gold QA File

The main gold QA dataset is:

```text
benchmarks/gold_qa/eval_multi_doc_rag.json
```

Each item contains:

- `id`: stable test id.
- `doc`: short document group label.
- `question`: user-style query.
- `expected_doc_title`: document that should be routed/retrieved.
- `expected_answer`: human reference answer for review.
- `must_have`: required facts. These drive most of the score.
- `should_have`: useful optional facts.
- `must_not_have`: wrong facts or drift from other PDFs.
- `max_words`: optional answer length budget.

`must_have`, `should_have`, and `must_not_have` may contain either strings or lists of acceptable alternatives.

Example:

```json
[
  "3D consistency",
  ["dynamic camera motion", "dynamic camera"]
]
```

This means the answer must contain `3D consistency`, and may satisfy the second requirement with either phrase.

## Gold QA Coverage Audit

Use the coverage audit after ingesting new PDFs or daily document batches:

```cmd
venv\Scripts\python.exe scripts\audit_gold_qa_coverage.py --env-file .env --output var\logs\gold_qa_coverage_report.json
```

It compares indexed SQLite documents, raw PDFs under `data/raw/documents`, and the gold QA file. The report highlights missing or undercovered indexed documents and unmatched eval items.

Use this as a gate when coverage must block the change:

```cmd
venv\Scripts\python.exe scripts\audit_gold_qa_coverage.py --fail-under-minimum
```

See [docs/GOLD_QA_COVERAGE.md](GOLD_QA_COVERAGE.md) for the full workflow.

## RAG Quality Eval

The main script is:

```text
scripts/eval_rag_quality.py
```

For every gold QA item, it runs the real orchestrator:

```text
deps.orchestrator.handle_query(...)
```

So the eval covers the actual path:

```text
planner -> document router -> retrieval -> evidence judge -> answer service -> verifier -> repair/retry
```

Run the full eval:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --eval-file benchmarks\gold_qa\eval_multi_doc_rag.json --output var\logs\rag_quality_report.json
```

Run selected items:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --ids docker_watchtower_features,ml_crfs
```

Run as a gate:

```cmd
venv\Scripts\python.exe scripts\eval_rag_quality.py --fail-under-average 8 --fail-under-item 7
```

## RAG Scoring

Each answer is scored out of 10:

- `5.0` required fact coverage from `must_have`.
- `1.0` optional detail coverage from `should_have`.
- `1.0` citation presence.
- `1.0` correct document routing/citation title.
- `1.0` verifier status is `verified`.
- `1.0` focus score.

Focus score is reduced when:

- the answer includes `must_not_have` content,
- the answer is longer than `max_words`,
- the answer falls back to an insufficient-information message.

Important report fields:

- `score`: total score out of 10.
- `missing_must_have`: required facts not found in the answer.
- `triggered_must_not_have`: unwanted facts found in the answer.
- `top_routed_doc`: top document selected by the router.
- `verification`: verifier result and issues.
- `citations`: final cited chunks.
- `routed_docs`: document router candidates.
- `answer`: actual model answer.

Generated reports are written under:

```text
eval/
```

Examples:

```text
var/logs/rag_quality_report.json
var/logs/rag_quality_batch_1_report.json
var/logs/rag_quality_regression_report.json
```

## Retrieval Eval

The retrieval-only script is:

```text
scripts/eval_retrieval.py
```

It does not judge final answers. It checks whether retrieval found expected pages and expected keywords.

Default command:

```cmd
venv\Scripts\python.exe scripts\eval_retrieval.py --output eval\retrieval_report.json
```

Retrieval scoring is also out of 10:

- `4.0` page score from expected page hits.
- `6.0` keyword score from expected keyword hits.

The retrieval report is useful when final answers are bad and we need to know whether the failure came from retrieval or answer generation.

Important retrieval report fields:

- `matched_pages`
- `missing_pages`
- `matched_keywords`
- `missing_keywords`
- `retrieved`
- `routed_docs`
- `retrieval_query`

## Memory Eval

The memory eval dataset is:

```text
benchmarks/memory/memory_multi_turn.json
```

The script is:

```text
scripts/eval_memory_quality.py
```

It uses a temporary SQLite database and evaluates the memory layer directly. It does not call the LLM, Qdrant, or PDF retrieval path, so it is fast and deterministic.

The current cases check:

- explicit project-rule capture,
- short-term follow-up context,
- user-preference capture,
- task-status recall for next-step planning,
- redaction of sensitive-looking short-term text.

Run:

```cmd
venv\Scripts\python.exe scripts\eval_memory_quality.py --output var\logs\memory_quality_report.json --fail-under-average 9 --fail-under-item 9
```

Memory scoring is out of 10:

- `5.0` required memory content from `must_include`.
- `2.0` safety score from `must_not_include`.
- `2.0` memory kind correctness from required and forbidden kinds.
- `1.0` expected memory-context sections.

Memory eval is separate from RAG eval. Memory can guide preferences and process, but PDF factual answers must still come from retrieved document chunks and citations.

## Regression Runner

The standard command is:

```cmd
venv\Scripts\python.exe scripts\run_regression.py
```

It runs:

- Python compile checks,
- memory smoke,
- memory eval smoke,
- SQLite threading smoke,
- document library smoke,
- feedback/eval candidate smoke tests,
- guardrails smoke,
- File MCP, SQLite MCP, and MCP adapter smoke,
- tool approval UI contract smoke,
- weather tool smoke,
- focused RAG quality eval.

Quick smoke-only check:

```cmd
venv\Scripts\python.exe scripts\run_regression.py --skip-rag
```

Full RAG benchmark:

```cmd
venv\Scripts\python.exe scripts\run_regression.py --full --output var\logs\rag_quality_report.json
```

## How We Use Eval Results

Use this process for quality work:

1. Add or update gold QA before optimizing.
2. Run a targeted eval for failing cases.
3. Inspect whether failure is routing, retrieval, evidence selection, answer generation, citation, verifier, or focus.
4. Make a general-purpose fix.
5. Run regression.
6. Run the full benchmark before large pushes.

Do not optimize using hardcoded document keywords. The goal is behavior that works for unseen PDFs.
