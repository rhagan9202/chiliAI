# Synthetic Policy Corpus — Deferred Work

## Context

The ingestion pipeline E2E demo spec (`2026-05-22-ingestion-pipeline-e2e-demo-design.md`) implements and tests the document ingestion path with **two tiny markdown fixtures** so the `LlmDocumentExtractor`, Ollama adapter, fallback chain, embed-and-index step, re-upload idempotency, and KB cascade delete are all exercised end to end. The fixtures live under `backend/tests/ingestion/fixtures/policies/`.

Authoring a realistic synthetic policy corpus that would let the demo show a meaningful **policy graph** (not just claims/providers) was **deferred** at the user's request. This file captures the work so a future implementer can pick it up cleanly without re-reading the parent spec.

## Goal

Produce a small (~10–25 document) corpus of synthetic Medicare policy documents that:

- Exercise multiple parser formats (PDF, DOCX, MD, HTML) so the parser registry gets real coverage.
- Reference the same entity types used by the records pipeline so the document graph and the records graph **join naturally** in the workbench view: `provider`, `claim`, `beneficiary`, plus document-side types like `policy`, `procedure_code`, `regulation_section`.
- Include enough relationships that LLM-driven extraction has something interesting to find: policy → governs → procedure_code; policy → applies_to → provider_specialty; policy → cites → regulation_section.
- Are realistic enough that the LLM extractor produces a useful graph without prompt engineering specific to one synthetic file.

## Suggested Document Shapes

A reasonable mix:

| Count | Format | Shape |
|------|--------|-------|
| 4–6  | PDF    | CMS-style policy bulletins (1–3 pages each) — billing rules, prior-authorization requirements, coverage limits. |
| 3–5  | DOCX   | Provider notification letters — changes in reimbursement rates, network participation rules, audit notices. |
| 4–8  | MD     | Internal policy explainers — plain-language summaries of CMS rules, FAQ documents, internal training material. |
| 2–3  | HTML   | Web pages mimicking Medicare Coverage Database (MCD) entries. |
| 1–2  | JSON   | Structured policy fact files (an "escape hatch" with no extraction ambiguity, useful for sanity tests). |

Total target: 20-ish documents, each 1–5 pages or equivalent.

## Suggested Entity & Relationship Coverage

Beyond the records-side entities (`provider`, `claim`, `beneficiary`), the policy corpus should cause extraction of:

- `policy` — natural key: `policy_id` (synthetic ID embedded in each doc, e.g. `POL-2024-INPATIENT-001`).
- `procedure_code` — natural key: `code` (use real CPT/HCPCS codes for realism; pick a small set, e.g. 10–20 codes from the inpatient and carrier files we know exist in DE-SynPUF).
- `regulation_section` — natural key: `citation` (e.g. `42 CFR 410.32`).
- Optional: `provider_specialty`, `drug` (NDC).

Relationships to coax:

- `policy → governs → procedure_code`
- `policy → applies_to → provider_specialty` or `provider`
- `policy → cites → regulation_section`
- `policy → effective_from / supersedes → policy`

Add these to `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` when authoring this corpus.

## Authoring Approach Options

Two paths, pick whichever is cheaper at the time:

1. **LLM-assisted authoring (recommended)** — Use a large cloud model with a careful prompt:
   > Generate a realistic CMS policy bulletin (~2 pages, plain text suitable for PDF conversion). The bulletin governs CPT codes {list}, cites 42 CFR {section}, applies to {specialty}, and is identified as policy {id}. Use authentic CMS bulletin language, sections, and formatting.

   Run the prompt 20+ times with varied inputs, save each output, then batch-convert MD/TXT → PDF (e.g. with `pandoc`) and TXT → DOCX (with `python-docx`). Cheap, fast, and the output is unambiguously synthetic — safe to ship in the repo if size allows or in `sample_data/policies/` if not.

2. **Manual authoring** — Pull 10–20 real CMS bulletin URLs as inspiration, rewrite each into a 1–2 page synthetic version with fictional policy IDs and dates. Slower but more controlled, and avoids any LLM-generated artifacts that might confuse the extractor.

## Where to Put the Files

- If total corpus size ≤ ~20 MB and the documents are unambiguously synthetic, check them into `backend/tests/ingestion/fixtures/policies/` so they live with the repo and CI uses them.
- Otherwise drop them in `sample_data/policies/` (gitignored alongside `sample_data/CMS/`) and update `sample_data/README.md` with the expected filenames and a download/generation script.

## Wiring

- Add a `policies` document feed to the medicare_fraud config if any policy-specific configuration is needed beyond what the existing parser registry handles. Most likely no config changes are needed — the existing document upload endpoint will pick up the new files automatically.
- Update `backend/tests/e2e/test_full_pipeline.py` to upload the corpus during the demo flow and assert that the expected policy entities + their relationships to providers/claims/procedure_codes appear in the graph.
- Update `make demo-tn-subset` to optionally upload the corpus after the records ingestion (gate behind a flag if the corpus is large).

## Pick-Up Checklist

- [ ] Decide authoring approach (LLM-assisted vs. manual).
- [ ] Author corpus following the shape and entity/relationship guidance above.
- [ ] Place files per the "Where to Put the Files" guidance.
- [ ] Update `medicare_fraud_cms_desynpuf.yaml` to declare any new entity types (`policy`, `procedure_code`, `regulation_section`, etc.) with natural keys and relationships.
- [ ] Run the LLM extractor against one document end to end manually and tune prompts in `LlmDocumentExtractor` if extraction quality is poor.
- [ ] Add an integration test that uploads the full corpus and asserts entity/relationship counts.
- [ ] Extend the E2E test to cover the combined records + documents graph.
- [ ] Update `make demo-tn-subset` to upload the corpus.
- [ ] Update READMEs and `docs/architecture.md` to reflect the broader document graph.

## Estimated Effort

A focused half day if LLM-assisted authoring goes well; up to two days if manual authoring + extraction tuning is needed.
