# Gold QA Coverage

Gold QA coverage keeps the RAG system honest as more PDFs are ingested. The goal is to measure whether important indexed documents have enough human-written questions before we optimize answer behavior.

## Why This Exists

The system should work for unseen PDFs, not only for Sora, Docker, or the first few test documents. For each important new document, add enough gold QA to test routing, retrieval, answer generation, verification, and citations.

Recommended minimum:

- `3` gold QA items per important indexed document.
- `5` gold QA items as the target for high-value documents.

Good question mix:

- definition question,
- feature or component question,
- how or why question,
- limitation, risk, or tradeoff question,
- practical use or application question.

Do not add hardcoded document-specific keywords to production code. If a benchmark fails, use the trace to find the generic failure type: routing, retrieval, evidence selection, answer generation, citation, verifier, or repair.

## Coverage Audit

Run the audit after ingesting new documents:

```powershell
venv\Scripts\python.exe scripts\audit_gold_qa_coverage.py --env-file .env --output var\logs\gold_qa_coverage_report.json
```

The audit compares:

- indexed documents from SQLite,
- raw PDFs under `data/raw/documents`,
- gold QA items in `benchmarks/gold_qa/eval_multi_doc_rag.json`.

The report shows:

- indexed document count,
- raw PDF count,
- unindexed PDF count,
- gold QA item count,
- documents with no matching QA,
- documents below the configured minimum,
- eval items that do not match any indexed document title.

Use a failing gate when you want CI or local regression to block missing coverage:

```powershell
venv\Scripts\python.exe scripts\audit_gold_qa_coverage.py --fail-under-minimum
```

## Add New Gold QA

Edit:

```text
benchmarks/gold_qa/eval_multi_doc_rag.json
```

Each item should include:

- `id`: stable lowercase id.
- `doc`: short document family label.
- `question`: natural user query.
- `expected_doc_title`: indexed document title or PDF title.
- `expected_answer`: concise reference answer.
- `must_have`: required facts.
- `should_have`: optional useful facts.
- `must_not_have`: facts that would indicate drift or wrong-document mixing.

After adding a batch, run focused quality eval:

```powershell
venv\Scripts\python.exe scripts\eval_rag_quality.py --ids new_case_id_1,new_case_id_2 --output var\logs\rag_quality_new_cases.json
```

Then run the standard regression gate:

```powershell
venv\Scripts\python.exe scripts\run_regression.py
```

## Coverage Workflow

1. Ingest new PDFs.
2. Run the coverage audit.
3. Add 3 to 5 gold QA items for missing or undercovered important documents.
4. Run focused RAG eval for the new IDs.
5. Fix only generic failures shown by traces.
6. Run full regression before merging.
