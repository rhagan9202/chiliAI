# Medicare Fraud Knowledge Base Fixtures

This directory contains development fixtures for testing chiliAI knowledge base ingestion, baseline extraction, validation, graph creation, Investigation search, and zero-entity completion behavior.

The fixtures intentionally use the configured Medicare Fraud Detection domain fields from `backend/config/defaults/medicare_fraud.yaml`:

- provider: `npi`, `specialty`, `state`
- beneficiary: `hic_number`, `age`, `chronic_conditions`
- claim: `claim_id`, `amount`, `service_date`, `procedure_codes`
- facility: `facility_id`, `name`, `type`

## Fixture matrix

| File | Purpose | Expected outcome |
| --- | --- | --- |
| `01_single_claim_complete.json` | Small positive graph smoke | Ready KB with provider/beneficiary/claim/facility graph data |
| `02_multi_claim_referral_network.json` | Multi-record JSON batch | Multiple claim-centered neighborhoods |
| `03_claims_batch.csv` | CSV parser + tabular extraction edge case | Partial graph data; numeric CSV values currently validate as strings |
| `04_unstructured_claim_note.txt` | Unstructured text extraction | Graph data from label/value lines in prose |
| `05_partial_missing_required_fields.json` | Missing required fields | Validation negative/partial extraction behavior |
| `06_zero_entity_resume_like.txt` | Non-domain document | Ready KB/document with zero entities and zero relationships |
| `07_invalid_values_and_decoys.txt` | Invalid values and noisy decoys | Validation warnings/rejections |
| `08_large_text_claim_bundle.txt` | Chunking stress | Larger text ingestion and graph construction smoke |
| `manifest.json` | Machine-readable expectations | Search queries and expected minimum graph counts |

## Manual development upload

With the dev stack running, create a KB in the UI or through the API, then upload one fixture at a time from this directory.

Example API flow from the repository root:

```bash
KB_ID=$(curl -sS -X POST http://localhost:8000/knowledgebases \
  -H 'Content-Type: application/json' \
  -d '{"name":"Fixture Smoke","description":"manual fixture upload"}' \
  | backend/.venv/bin/python -c 'import json, sys; print(json.load(sys.stdin)["id"])')

curl -sS -X POST "http://localhost:8000/knowledgebases/$KB_ID/documents" \
  -F "files=@docs/testing/knowledge_base_fixtures/medicare_fraud/01_single_claim_complete.json;type=application/json"

curl -sS "http://localhost:8000/knowledgebases/$KB_ID"
```

Then open:

```text
http://localhost:5173/knowledgebases/<KB_ID>
http://localhost:5173/investigation?kb_id=<KB_ID>
```

Use the Investigation entity search box with one of the `search_queries` listed in `manifest.json`, such as `CLAIM-FIXTURE-001`.

## Regression scenarios

### Positive graph creation

Use `01_single_claim_complete.json`, `02_multi_claim_referral_network.json`, `04_unstructured_claim_note.txt`, and `08_large_text_claim_bundle.txt` to verify:

1. Upload returns `202 Accepted`.
2. Worker emits graph update and KB ready events.
3. KB detail eventually reports `ready`.
4. Investigation search finds at least one configured property value.
5. Entity detail and neighborhood endpoints return graph data.

### Zero-entity terminal completion

Use `06_zero_entity_resume_like.txt` to verify:

1. Upload parses and chunks successfully.
2. No configured Medicare entities are extracted.
3. KB and document still reach `ready`.
4. Graph counts remain `0`.

### Validation and warning behavior

Use `03_claims_batch.csv`, `05_partial_missing_required_fields.json`, and `07_invalid_values_and_decoys.txt` to verify that invalid or incomplete candidates do not produce misleading graph state. The CSV fixture is useful for preserving today’s known edge case: numeric-looking CSV values are rendered as strings before validation, so some candidates validate and others are rejected.

## Notes

- The current baseline extractor is label/pattern based. Keep fixture labels close to configured property names when the intent is positive extraction.
- The fixture documents are synthetic and contain no real patient, provider, or billing data.
- Expected counts are minimums, not exact assertions. Chunking, validation, and deduplication behavior may change as the extraction pipeline evolves.
