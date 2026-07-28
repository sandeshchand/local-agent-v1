# Chunking Strategy

Chunking converts parsed PDF pages into clean, searchable text units for SQLite and Qdrant.

The implementation is in:

```text
src/local_agent/ingestion/parsers/pdf_parser.py
src/local_agent/ingestion/chunking.py
src/local_agent/ingestion/metadata.py
src/local_agent/ingestion/pipeline.py
```

## High-Level Flow

```text
PDF file
-> parse pages
-> extract or infer page section title
-> clean page text
-> split into chunks
-> remove low-value chunks
-> embed chunks
-> store metadata in SQLite
-> store vectors and payloads in Qdrant
```

## PDF Parsing

`parse_pdf()` uses `pypdf.PdfReader`.

For each PDF:

- `doc_id` is the first 16 characters of the SHA-256 checksum.
- `checksum` is the full SHA-256 file hash.
- `title` comes from PDF metadata, falling back to the file stem.
- `source_path`, `page_count`, and parsed pages are stored.

For each page:

- text is extracted with `page.extract_text()`,
- if the page has too little searchable text, optional OCR is attempted,
- a page section title is inferred from heading-like lines,
- the previous section title can be reused as fallback.

If no page has searchable text and OCR is unavailable, ingestion raises a scanned-PDF error.

## Section Title Detection

Section titles are inferred from early page lines.

The parser rejects obvious boilerplate such as:

- URLs,
- Medium navigation text,
- dates and reading-time lines,
- author/profile/footer lines,
- recommendation blocks.

It accepts heading-like lines when they are short, title-like, not boilerplate, and often numbered or capitalized.

The section title is stored on each chunk as:

```text
section_title
```

This helps routing, retrieval boosts, evidence selection, trace inspection, and citations.

## Text Cleanup

Before splitting, `normalize_page_text()`:

- normalizes newlines,
- removes null and non-breaking spaces,
- trims repeated blank lines,
- removes known boilerplate lines,
- stops when terminal boilerplate is reached,
- repairs simple hyphenation such as `exam- ple` into `example`.

Terminal boilerplate can stop chunking for the remaining page flow. This is useful for Medium-style PDFs where the end of the article contains recommendations and response sections.

## Split Strategy

The splitter is recursive and conservative:

1. If text is already within `chunk_size`, keep it as one chunk.
2. Try paragraph splitting first.
3. If a paragraph is too large, split by sentence.
4. If a sentence is still too large, split by character window with safe boundaries.

Large-text splitting tries to end near:

- sentence punctuation,
- whitespace,
- comma/semicolon/colon/closing parenthesis.

It also tries to start the next chunk at a safe boundary.

## Chunk Size And Overlap

The ingestion pipeline accepts:

```text
CHUNK_SIZE
CHUNK_OVERLAP
```

Current defaults from config loading:

```text
CHUNK_SIZE=900
CHUNK_OVERLAP=120
```

`chunk_size` is character-based, not a tokenizer count. The stored `token_estimate` is:

```text
max(1, len(chunk_text) // 4)
```

Overlap is used only when splitting very large continuous text. Paragraph and sentence splits avoid unnecessary overlap to keep chunks cleaner.

## Low-Value Chunk Filtering

Short chunks are dropped when they look low-value.

A chunk shorter than 80 characters is considered low-value when it has:

- no sentence punctuation,
- no code-like marker.

This keeps navigation fragments, headings without context, and boilerplate from polluting retrieval.

## Chunk Metadata

Each chunk has:

```text
chunk_id
doc_id
chunk_index
page_number
text
token_estimate
section_title
```

Chunk ids use:

```text
{doc_id}-p{page_number}-c{chunk_index}
```

`chunk_index` is sequential inside the document.

## Storage

SQLite stores:

- document metadata in `documents`,
- chunk metadata and text in `chunks`.
- latest ingestion attempt metadata in `document_ingestion_status`.

Qdrant stores:

- embedding vector,
- payload with document title, source path, page number, section title, chunk id, and text.

The Qdrant point id is a deterministic numeric hash of `chunk_id`.

## Ingestion Status And Versions

Ingestion now records production metadata for each document:

```text
ingestion_status
parser_version
chunking_version
embedding_model
chunk_size
chunk_overlap
chunk_count
last_ingest_error
```

The active version constants are defined in:

```text
src/local_agent/ingestion/metadata.py
```

Default ingestion is incremental:

```powershell
local-agent ingest --path data\raw\documents
```

If a PDF has the same checksum, parser version, chunking version, embedding model, chunk size, and chunk overlap as the stored index, it is skipped. This lets daily batch ingestion run safely across large folders without rebuilding unchanged documents.

Force rebuild a document or folder with:

```powershell
local-agent ingest --path data\raw\documents --force
```

Use `--force` after a deliberate re-index decision, for example when validating a new chunking strategy.

During re-ingestion, the pipeline removes old SQLite chunks and old Qdrant vectors for the affected `doc_id` before writing the new index. This prevents stale vectors from older chunking runs from being retrieved.

## Retrieval Context Expansion

Chunking creates relatively focused chunks, but a final answer often needs nearby context. Retrieval therefore expands around the highest-ranked chunks after dense search, BM25, RRF fusion, and reranking.

The implementation is in:

```text
src/local_agent/retrieval/context_expansion.py
src/local_agent/retrieval/query_terms.py
src/local_agent/storage/sqlite_store.py
```

The flow is:

```text
top ranked chunks
-> add previous/next chunks from the same document
-> add matching chunks from the same section
-> add chunks whose section titles match query terms
-> optionally build parent context windows
-> pass expanded context to evidence selection and answering
```

Neighbor chunks are loaded through:

```python
SQLiteStore.get_neighbor_chunks(doc_id, chunk_index, window)
```

Important safeguards:

- neighbors are filtered by the same `doc_id`, so context never crosses into another PDF,
- duplicate `chunk_id`s are skipped,
- anchor chunks get `neighbor_role="anchor"`,
- nearby chunks get `source="neighbor"` and `neighbor_role="context"`,
- each neighbor stores `anchor_chunk_id`, so traces can show which retrieved chunk caused the expansion.

Current retrieval defaults:

```text
neighbor_window=2
use_parent_context=True
parent_window=3
parent_max_chars=4200
final_context_limit=24
```

That means each strong anchor can bring up to two chunks before and two chunks after it. Parent context can then combine nearby child chunks into a larger focused context block when the query terms appear in that window.

This helps with PDFs where the exact answer is split across adjacent chunks, for example:

- a heading is in one chunk and the list is in the next,
- an explanation starts before the retrieved chunk,
- a numbered list continues after the retrieved chunk,
- Medium-style articles place key context around headings and short paragraphs.

This is not document-specific optimization. It is a general RAG strategy for preserving local continuity after chunking.

## When To Reingest

Reingest documents when changing:

- parser cleanup,
- OCR behavior,
- section-title detection,
- chunk size,
- chunk overlap,
- low-value filtering,
- embedding model.

If the change is represented by `PARSER_VERSION` or `CHUNKING_VERSION`, normal ingestion will detect that the stored index is outdated and rebuild the affected PDFs. If you are testing a one-off rebuild without a version bump, use `--force`.

If the embedding model changes vector dimension, reset or migrate the Qdrant collection before re-ingesting. The incremental re-ingest flow cleans vectors by document, but it does not silently recreate a whole Qdrant collection.

For a local reset, follow the reset instructions in `README.md`.

## Design Goal

The goal is not to create document-specific chunks. The strategy is general-purpose:

- preserve semantic paragraphs when possible,
- keep enough local context for answer generation,
- avoid noisy Medium/PDF boilerplate,
- retain page and section metadata for citations and debugging,
- support unseen PDFs without hardcoded document keywords.

