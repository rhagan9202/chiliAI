# Knowledge Base Test Fixtures

Synthetic documents for development and regression testing of chiliAI knowledge base ingestion, extraction, validation, graph creation, and Investigation search.

## Available fixture packs

| Pack | Domain config | Purpose |
| --- | --- | --- |
| `medicare_fraud/` | `backend/config/defaults/medicare_fraud.yaml` | Medicare fraud domain fixtures covering positive graph creation, partial validation, noisy/invalid values, chunking stress, and zero-entity completion |

## Usage

Start with the domain-specific `README.md` and `manifest.json` inside each fixture pack. The manifest is intended to be consumed by future smoke tests and contains expected minimum graph counts plus useful Investigation search queries.

These files are synthetic and safe to commit. Do not place real PHI, PII, credentials, or customer data in this directory.
