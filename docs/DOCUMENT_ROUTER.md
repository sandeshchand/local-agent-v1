# Document Router

The document router is the first retrieval stage for multi-PDF RAG.

The implementation is in:

```text
src/local_agent/retrieval/doc_router.py
src/local_agent/agent/orchestrator.py
src/local_agent/storage/sqlite_store.py
```

## Purpose

When many PDFs are indexed, retrieval should not always search every chunk first.

The document router ranks documents for a query and returns the most likely document candidates. Chunk retrieval then searches inside those candidates.

This improves:

- answer relevance,
- retrieval speed,
- resistance to cross-document drift,
- quality for multi-PDF questions.

## Inputs

The router receives:

```text
query
top_n
```

It loads document metadata through:

```text
SQLiteStore.list_documents_for_routing()
```

Each document includes:

- `doc_id`
- `title`
- `source_path`
- `page_count`
- `indexed_at`
- aggregated `section_titles`

The router also reads chunk text for each document, up to a maximum amount, so routing can use actual document content.

## Routing Text

For each document, the router builds searchable text from:

```text
title
file basename
section titles
chunk text
```

This means routing can match:

- document titles,
- PDF filenames,
- section headings,
- distinctive terms in the document body.

## Document Routing Vs Chunk Retrieval

The system uses two levels of search.

First, the document router chooses likely PDFs:

```text
User query
-> BM25 over document-level text
-> title/path/section/content boosts
-> top document candidates
```

This is mostly keyword/BM25 style ranking with extra boosts for strong document signals.

Then chunk retrieval searches inside the selected documents:

```text
selected doc_ids
-> dense semantic search with Qdrant embeddings
-> BM25 keyword search over chunks
-> RRF fusion
-> cross-encoder reranking
-> neighbor and section context expansion
-> evidence selection
```

So the accurate mental model is:

```text
Document level:
BM25 + routing boosts selects likely PDFs.

Chunk level:
Hybrid semantic + keyword retrieval searches inside those PDFs.
```

Example:

```text
Question: What are the key features of WatchTower?
```

The router may rank the Docker PDF highest because the title, section titles, or document text mention Docker/WatchTower. Then chunk retrieval searches inside that selected Docker PDF to find the exact WatchTower feature chunks.

## Scoring

The router uses BM25 plus custom boosts.

Base score:

```text
BM25(query_tokens, document_routing_text)
```

Boosts include:

- title token matches,
- section-title token matches,
- path token matches,
- content frequency matches,
- coverage of query tokens,
- exact phrase matches,
- distinctive query terms.

Distinctive terms are things like:

- capitalized names,
- acronyms,
- hyphenated terms,
- terms with digits,
- terms with underscores.

This helps route queries like:

- `WatchTower`
- `LazyDocker`
- `Sora`
- `CRF`
- `PydanticAI`

without hardcoding any one PDF.

## Candidate Selection In Orchestrator

The orchestrator calls:

```text
doc_router.route(retrieval_query, top_n=3)
```

Then `_candidate_doc_ids()` decides whether to search:

- only the top document, or
- all top routed documents.

If the top routed document is clearly ahead, only that `doc_id` is used.

Current rule:

```text
top_score >= second_score * 1.05
or
top_score - second_score >= 3.0
```

If scores are close, the system searches all routed candidates to avoid losing relevant evidence.

## Retry Behavior

If answer verification fails or no citable evidence is found, the orchestrator can retry retrieval with:

```text
broaden_doc_scope = True
```

That retry searches all documents instead of only routed candidates.

This is a general recovery path for:

- wrong document routing,
- ambiguous queries,
- unseen PDFs,
- noisy titles,
- weak section headings.

## Trace Visibility

The retrieve trace step stores:

- `candidate_scope`
- `candidate_doc_count`
- `routed_docs`
- `routing_score`
- `result_count`
- `selected_count`
- `answer_context_count`

In the UI, open:

```text
Workspace -> Trace -> Timeline
```

This helps identify whether a bad answer came from:

- wrong routed document,
- weak chunk retrieval,
- evidence selection,
- answer generation,
- verifier/repair.

## Common Failure Cases

Wrong document routing can happen when:

- multiple PDFs share similar terms,
- titles are noisy,
- extracted text is noisy,
- the query lacks a distinctive entity,
- the relevant document has weak OCR/text extraction,
- the user asks a broad question without naming the document.

Use eval report fields:

- `top_routed_doc`
- `routed_docs`
- `routing_score`
- `missing_must_have`

## Design Rules

- Do not hardcode document names for special treatment.
- Use title, path, section, and chunk content generically.
- Keep full-corpus retry available as a safety net.
- Use eval to validate routing changes across multiple PDFs.
