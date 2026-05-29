# Evaluation

This project uses repeatable local evaluation to check whether RAG changes improve answer quality without overfitting to one PDF.

## Evaluation Layers

There are three useful evaluation layers:

- RAG answer quality eval: checks the final answer, citations, routing, verifier status, and drift.
- Retrieval eval: checks whether retrieval returned the expected pages and keywords before answer generation.
- Regression runner: runs compile checks, smoke tests, and a focused RAG quality gate before commits.

## Gold QA File

The main gold QA dataset is:

```text
test/eval_multi_doc_rag.json
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
venv\Scripts\python.exe scripts\eval_rag_quality.py --eval-file test\eval_multi_doc_rag.json --output eval\rag_quality_report.json
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
eval/rag_quality_report.json
eval/rag_quality_batch_1_report.json
eval/rag_quality_regression_report.json
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

## Regression Runner

The standard command is:

```cmd
venv\Scripts\python.exe scripts\run_regression.py
```

It runs:

- Python compile checks,
- memory smoke,
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
venv\Scripts\python.exe scripts\run_regression.py --full --output eval\rag_quality_report.json
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

