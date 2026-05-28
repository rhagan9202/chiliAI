# Ingestion Module

`ingestion/` handles document parsing, chunking, entity/relationship extraction, and registration for the chiliAI platform. It is the document-pipeline counterpart to `records/` (tabular feeds).

## Extractors

### PatternDocumentExtractor (default)

Regex/heuristic extractor. Used when no LLM client is configured or as a fast fallback. Produces lower-recall extractions suitable for smoke tests and offline environments.

### LlmDocumentExtractor

Schema-driven LLM extractor introduced in the `feature/ingestion-pipeline-e2e-demo` branch. Key behaviors:

- **Schema-driven prompts** — Derives the extraction prompt from `DomainConfig.entities` and `DomainConfig.relationships` at construction time, so the same extractor code works for any configured domain.
- **JSON-mode parsing** — Requests a structured JSON response from the LLM. The extractor strips markdown fences (` ```json ... ``` `) before parsing to tolerate models that wrap the payload.
- **Required-property validation** — After parsing, validates that each extracted entity has all required properties declared in the domain config. Entities failing validation are logged and dropped rather than propagated as malformed data.
- **Natural-key deduplication** — Within a single chunk's extraction pass, entities that map to the same natural key (type + identifying property value) are merged so the same real-world entity appearing twice in a paragraph is not double-counted.
- **Intra-chunk relationship pass** — A second LLM call (or a second JSON block in the same response) identifies relationships between entities extracted in the same chunk.
- **Fallback** — When `IngestionService` is constructed without an `LlmClientProtocol` dependency, it falls back to `PatternDocumentExtractor` automatically. No config change is needed; the fallback is determined by whether a client is injected.

## Content-Hash Idempotency

Document registration is idempotent per knowledge base. The ingestion service derives a deterministic `source_document_id` from the SHA-256 hash of the file content (or a URI hash for remote sources). Re-uploading the same bytes produces the same ID and does not publish a duplicate `documents.uploaded` event. The `DocumentUploadReceipt` includes a `replaced_document_id` field when an existing document with the same natural key was superseded (re-upload semantics).

## Provenance Metadata

Every `Entity` and `Relationship` emitted by the extractor carries provenance fields (`source_kind="document"`, `source_document_id`, `source_chunk_id`) so downstream cascade-delete and audit queries can trace data back to its source. See `backend/graph/README.md` for the full provenance contract.

## Parser Registry

Parsers for PDF, DOCX, HTML, TXT, JSON, CSV, and XLSX are registered in `parsers/registry.py`. The HTML parser currently normalizes visible text; richer heading/link/table fidelity is tracked separately in `docs/backlog/ingestion.md` as `ingestion.02`.

## Commands

```bash
pip install -e ".[dev]"
pytest tests/ingestion -m "not integration"    # fast unit tests
pytest tests/ingestion -m integration          # needs a configured LLM adapter
```

See [`docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md`](../../docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md) for the end-to-end demo context.
