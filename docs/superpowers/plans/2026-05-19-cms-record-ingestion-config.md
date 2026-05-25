# CMS Record Ingestion Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure the Medicare CMS DE-SynPUF files in `sample_data/CMS/` as structured record feeds that land safely in `raw_records` and produce useful graph entities without dropping duplicate claim segments.

**Architecture:** Keep the database schema generic: the existing `raw_records` table remains the canonical landing zone, with typed payloads stored in JSONB and idempotency keyed by `(knowledge_base_id, record_type, record_id)`. Add only the minimum records runtime support required by the sample files: blank-cell normalization, CMS `YYYYMMDD` date coercion, and composite record IDs for segmented claims. Add a CMS-specific domain config rather than destabilizing the current default `claims_feed` tests.

**Tech Stack:** Python 3.12, Pydantic `DomainConfig`, FastAPI records router, Postgres/TimescaleDB `raw_records`, YAML domain config, pytest.

---

## Findings From `sample_data/CMS/`

Files to support:

- `DE1_0_2008_Beneficiary_Summary_File_Sample_1.csv`: 116,352 data rows, 32 columns, unique `DESYNPUF_ID`.
- `DE1_0_2009_Beneficiary_Summary_File_Sample_1.csv`: 114,538 data rows, 32 columns, unique `DESYNPUF_ID`.
- `DE1_0_2010_Beneficiary_Summary_File_Sample_1.csv`: 112,754 data rows, 32 columns, unique `DESYNPUF_ID`.
- `DE1_0_2008_to_2010_Carrier_Claims_Sample_1A.csv`: 2,370,667 data rows, 142 columns, unique `CLM_ID`.
- `DE1_0_2008_to_2010_Carrier_Claims_Sample_1B.csv`: 2,370,668 data rows, 142 columns, unique `CLM_ID`.
- `DE1_0_2008_to_2010_Inpatient_Claims_Sample_1.csv`: 66,773 data rows, 81 columns, `CLM_ID` has 68 duplicate segment rows.
- `DE1_0_2008_to_2010_Outpatient_Claims_Sample_1.csv`: 790,790 data rows, 76 columns, `CLM_ID` has 10,975 duplicate segment rows.
- `DE1_0_2008_to_2010_Prescription_Drug_Events_Sample_1.csv`: 5,552,421 data rows, 8 columns, unique `PDE_ID`.

Current constraints that affect configuration:

- `CsvFileSource` returns every CSV column, including blank cells as `""`.
- `validate_rows()` rejects columns not listed in `record_schema`.
- `PropertyType.DATE` currently accepts ISO dates, but the CMS files use `YYYYMMDD`.
- `RecordFeedConfig.id_field` is a single source field; inpatient and outpatient need a composite key such as `CLM_ID:SEGMENT`.
- `RecordEntityMapping` and `RecordRelationshipMapping` do not skip blank optional IDs, so provider mappings should be limited until blank-ID handling exists.

## File Structure

- Modify: `backend/records/adapters/sources/file_source.py`
  - Normalize blank CSV cells to absent values so optional numeric/date fields do not fail coercion.
- Modify: `backend/records/validation.py`
  - Coerce CMS `YYYYMMDD` strings for `date` properties into ISO `YYYY-MM-DD` strings before validation.
- Modify: `backend/config/schema.py`
  - Add optional `id_template: str | None` to `RecordFeedConfig` and validate referenced template fields against `record_schema`.
- Modify: `backend/records/service.py`
  - Resolve `record_id` from `id_template` when present, otherwise keep `id_field`.
- Create: `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`
  - CMS-specific Medicare config with exhaustive `records.feeds` schemas for the eight CSV files.
- Test: `backend/tests/records/test_sources.py`
  - Cover blank CSV cell normalization.
- Test: `backend/tests/records/test_validation.py`
  - Cover `YYYYMMDD` date coercion.
- Test: `backend/tests/records/test_config.py`
  - Cover valid and invalid `id_template` references.
- Test: `backend/tests/records/test_service.py`
  - Cover composite record IDs.
- Test: `backend/tests/config/test_loader.py`
  - Ensure the CMS config loads.
- Optional fixture: `backend/tests/records/fixtures/cms/`
  - Add tiny representative CSV snippets, not full sample files.

## Configuration Shape

Use one feed per physical CMS file shape, with separate yearly beneficiary feeds to preserve annual snapshots in `raw_records`:

- `cms_beneficiary_summary_2008`, `record_type: cms_beneficiary_summary_2008`, `id_field: DESYNPUF_ID`
- `cms_beneficiary_summary_2009`, `record_type: cms_beneficiary_summary_2009`, `id_field: DESYNPUF_ID`
- `cms_beneficiary_summary_2010`, `record_type: cms_beneficiary_summary_2010`, `id_field: DESYNPUF_ID`
- `cms_carrier_claims_a`, `record_type: cms_carrier_claim`, `id_field: CLM_ID`
- `cms_carrier_claims_b`, `record_type: cms_carrier_claim`, `id_field: CLM_ID`
- `cms_inpatient_claims`, `record_type: cms_inpatient_claim_segment`, `id_template: "{CLM_ID}:{SEGMENT}"`
- `cms_outpatient_claims`, `record_type: cms_outpatient_claim_segment`, `id_template: "{CLM_ID}:{SEGMENT}"`
- `cms_prescription_drug_events`, `record_type: cms_prescription_drug_event`, `id_field: PDE_ID`

Graph mapping for the first implementation pass:

- Beneficiary summary feeds map to `beneficiary` using `DESYNPUF_ID`.
- Carrier feeds map to `claim` and `beneficiary`, with `billed_for` relationship. Do not map provider until blank provider IDs can be skipped safely.
- Inpatient/outpatient feeds map to `claim`, `beneficiary`, and `facility`, with `billed_for` and `performed_at`.
- PDE feed maps to `claim` and `beneficiary`, treating `PDE_ID` as a claim-like event ID unless a later domain config adds a dedicated `drug` entity and prescription relationship.

## Tasks

### Task 1: Normalize CSV Blanks

**Files:**
- Modify: `backend/records/adapters/sources/file_source.py`
- Test: `backend/tests/records/test_sources.py`

- [ ] **Step 1: Write the failing CSV source test**

Add a test that parses a row with an empty optional cell and expects that key to be absent:

```python
def test_csv_source_omits_blank_cells() -> None:
    source = CsvFileSource()
    rows = source.read_rows(b"claim_id,optional_amount\nc1,\n")
    assert rows == [{"claim_id": "c1"}]
```

- [ ] **Step 2: Run the targeted source test**

Run: `uv run --project backend pytest backend/tests/records/test_sources.py::test_csv_source_omits_blank_cells -q`

Expected: FAIL because the current parser returns `{"optional_amount": ""}`.

- [ ] **Step 3: Implement blank-cell omission**

In `CsvFileSource.read_rows()`, change the value handling so `""` is skipped the same way `None` is skipped:

```python
if value is None or value == "":
    continue
```

- [ ] **Step 4: Verify the source test**

Run: `uv run --project backend pytest backend/tests/records/test_sources.py::test_csv_source_omits_blank_cells -q`

Expected: PASS.

### Task 2: Coerce CMS Dates

**Files:**
- Modify: `backend/records/validation.py`
- Test: `backend/tests/records/test_validation.py`

- [ ] **Step 1: Write the failing date coercion test**

```python
def test_coerce_row_coerces_cms_yyyymmdd_date() -> None:
    schema = {
        "service_date": PropertyDefinition(type=PropertyType.DATE, display="Service Date")
    }
    coerced = coerce_row({"service_date": "20100312"}, schema)
    assert coerced["service_date"] == "2010-03-12"
```

- [ ] **Step 2: Run the targeted validation test**

Run: `uv run --project backend pytest backend/tests/records/test_validation.py::test_coerce_row_coerces_cms_yyyymmdd_date -q`

Expected: FAIL because date strings are not normalized.

- [ ] **Step 3: Implement date normalization**

In `_coerce_value()`, add a `PropertyType.DATE` branch that accepts ISO dates as-is and converts eight-digit CMS dates:

```python
if property_type is PropertyType.DATE:
    if len(text) == 8 and text.isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text
```

- [ ] **Step 4: Verify the validation test**

Run: `uv run --project backend pytest backend/tests/records/test_validation.py::test_coerce_row_coerces_cms_yyyymmdd_date -q`

Expected: PASS.

### Task 3: Support Composite Record IDs

**Files:**
- Modify: `backend/config/schema.py`
- Modify: `backend/records/service.py`
- Test: `backend/tests/records/test_config.py`
- Test: `backend/tests/records/test_service.py`

- [ ] **Step 1: Write config validation tests for `id_template`**

Add one test proving `{CLM_ID}:{SEGMENT}` is accepted when both fields exist in `record_schema`, and one test proving `{MISSING}` is rejected.

- [ ] **Step 2: Add `id_template` to `RecordFeedConfig`**

Add the field:

```python
id_template: str | None = None
```

Then extend `DomainConfig._validate_cross_references()` to extract `{field}` references from `id_template` and ensure each referenced field exists in `record_schema`.

- [ ] **Step 3: Write the service test for composite IDs**

Create a feed with `id_field: CLM_ID`, `id_template: "{CLM_ID}:{SEGMENT}"`, and rows:

```python
[
    {"CLM_ID": "c1", "SEGMENT": "1"},
    {"CLM_ID": "c1", "SEGMENT": "2"},
]
```

Assert persisted `record_id` values are `{"c1:1", "c1:2"}` and `accepted_count == 2`.

- [ ] **Step 4: Implement ID resolution in `RecordsService`**

Add a helper:

```python
def _resolve_record_id(feed: RecordFeedConfig, row: dict[str, object]) -> str:
    if feed.id_template is None:
        raw_id = row.get(feed.id_field)
        if raw_id is None:
            raise RecordValidationError(
                f"Feed '{feed.name}' record is missing id field '{feed.id_field}'."
            )
        return str(raw_id)
    try:
        return feed.id_template.format(**row)
    except KeyError as exc:
        missing = str(exc).strip("'")
        raise RecordValidationError(
            f"Feed '{feed.name}' record is missing id template field '{missing}'."
        ) from exc
```

Use that helper when constructing `RawRecord`.

- [ ] **Step 5: Verify records tests**

Run: `uv run --project backend pytest backend/tests/records/test_config.py backend/tests/records/test_service.py -q`

Expected: PASS.

### Task 4: Add CMS Domain Config

**Files:**
- Create: `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`
- Test: `backend/tests/config/test_loader.py`

- [ ] **Step 1: Create the config from the existing Medicare config**

Copy the non-record sections from `backend/config/defaults/medicare_fraud_dev.yaml` if this config is intended for the dev stack, or from `backend/config/defaults/medicare_fraud.yaml` if it should be local/in-memory by default.

- [ ] **Step 2: Add CMS feed schemas**

For every CMS feed, declare every CSV header in `record_schema`; otherwise validation rejects the upload as containing unexpected properties.

Use these required fields:

```yaml
cms_beneficiary_summary_2008:
  required: [DESYNPUF_ID, BENE_BIRTH_DT, SP_STATE_CODE, BENE_COUNTY_CD]
cms_beneficiary_summary_2009:
  required: [DESYNPUF_ID, BENE_BIRTH_DT, SP_STATE_CODE, BENE_COUNTY_CD]
cms_beneficiary_summary_2010:
  required: [DESYNPUF_ID, BENE_BIRTH_DT, SP_STATE_CODE, BENE_COUNTY_CD]
cms_carrier_claims_a:
  required: [DESYNPUF_ID, CLM_ID, CLM_FROM_DT, CLM_THRU_DT, LINE_NCH_PMT_AMT_1, LINE_ALOWD_CHRG_AMT_1]
cms_carrier_claims_b:
  required: [DESYNPUF_ID, CLM_ID, CLM_FROM_DT, CLM_THRU_DT, LINE_NCH_PMT_AMT_1, LINE_ALOWD_CHRG_AMT_1]
cms_inpatient_claims:
  required: [DESYNPUF_ID, CLM_ID, SEGMENT, PRVDR_NUM, CLM_PMT_AMT, CLM_ADMSN_DT, NCH_BENE_DSCHRG_DT]
cms_outpatient_claims:
  required: [DESYNPUF_ID, CLM_ID, SEGMENT, PRVDR_NUM, CLM_PMT_AMT]
cms_prescription_drug_events:
  required: [DESYNPUF_ID, PDE_ID, SRVC_DT, PROD_SRVC_ID, QTY_DSPNSD_NUM, DAYS_SUPLY_NUM, PTNT_PAY_AMT, TOT_RX_CST_AMT]
```

Use `date` for `*_DT` fields after Task 2, `decimal` for amount/quantity fields, `integer` for count/code fields only when blanks are not expected, and `string` for diagnosis/procedure/NPI fields that may include leading zeroes or alphanumeric codes.

- [ ] **Step 3: Add graph mappings**

Beneficiary summary:

```yaml
entities:
  - entity_type: beneficiary
    id_field: DESYNPUF_ID
    property_fields:
      hic_number: DESYNPUF_ID
```

Carrier:

```yaml
entities:
  - entity_type: claim
    id_field: CLM_ID
    property_fields:
      claim_id: CLM_ID
      amount: LINE_NCH_PMT_AMT_1
      service_date: CLM_FROM_DT
  - entity_type: beneficiary
    id_field: DESYNPUF_ID
    property_fields:
      hic_number: DESYNPUF_ID
relationships:
  - relationship_type: billed_for
    source_entity_type: claim
    target_entity_type: beneficiary
```

Inpatient/outpatient:

```yaml
entities:
  - entity_type: claim
    id_field: CLM_ID
    property_fields:
      claim_id: CLM_ID
      amount: CLM_PMT_AMT
      service_date: CLM_FROM_DT
  - entity_type: beneficiary
    id_field: DESYNPUF_ID
    property_fields:
      hic_number: DESYNPUF_ID
  - entity_type: facility
    id_field: PRVDR_NUM
    property_fields:
      facility_id: PRVDR_NUM
relationships:
  - relationship_type: billed_for
    source_entity_type: claim
    target_entity_type: beneficiary
  - relationship_type: performed_at
    source_entity_type: claim
    target_entity_type: facility
```

PDE:

```yaml
entities:
  - entity_type: claim
    id_field: PDE_ID
    property_fields:
      claim_id: PDE_ID
      amount: TOT_RX_CST_AMT
      service_date: SRVC_DT
  - entity_type: beneficiary
    id_field: DESYNPUF_ID
    property_fields:
      hic_number: DESYNPUF_ID
relationships:
  - relationship_type: billed_for
    source_entity_type: claim
    target_entity_type: beneficiary
```

- [ ] **Step 4: Add loader test**

Add:

```python
def test_load_cms_desynpuf_config() -> None:
    cfg = load_config("config/defaults/medicare_fraud_cms_desynpuf.yaml")
    feed_names = {feed.name for feed in cfg.records.feeds}
    assert "cms_prescription_drug_events" in feed_names
    assert "cms_inpatient_claims" in feed_names
```

- [ ] **Step 5: Verify config loading**

Run: `uv run --project backend pytest backend/tests/config/test_loader.py::test_load_cms_desynpuf_config -q`

Expected: PASS.

### Task 5: Add Tiny End-to-End Record Fixtures

**Files:**
- Create: `backend/tests/records/fixtures/cms/beneficiary_2008.csv`
- Create: `backend/tests/records/fixtures/cms/inpatient.csv`
- Create: `backend/tests/records/fixtures/cms/outpatient.csv`
- Create: `backend/tests/records/fixtures/cms/pde.csv`
- Test: `backend/tests/api/test_records_router.py`

- [ ] **Step 1: Create minimal fixture rows**

Use one or two rows per file. Include an inpatient or outpatient duplicate `CLM_ID` with different `SEGMENT` to prove composite IDs preserve both records.

- [ ] **Step 2: Add API upload tests against the CMS config**

Set `CHILI_CONFIG_PATH=config/defaults/medicare_fraud_cms_desynpuf.yaml`, upload each fixture through `POST /records/{knowledge_base_id}/files`, and assert `202` plus expected `accepted_count`.

- [ ] **Step 3: Verify API tests**

Run: `uv run --project backend pytest backend/tests/api/test_records_router.py -q`

Expected: PASS.

## Verification

- Run targeted records/config tests:

```bash
uv run --project backend pytest backend/tests/records backend/tests/config/test_loader.py backend/tests/api/test_records_router.py -q
```

- Load the CMS config directly:

```bash
CHILI_CONFIG_PATH=config/defaults/medicare_fraud_cms_desynpuf.yaml uv run --project backend python -c "from config.loader import load_config; cfg=load_config(); print(len(cfg.records.feeds))"
```

Expected output: `8`.

- For dev-stack verification, run migrations and upload a tiny fixture with `database.backend=postgres`, then confirm rows exist in `raw_records` for all configured record types.

## Open Questions

- Whether to model prescription events as `claim` for first-pass graph compatibility, or add dedicated `drug` / `prescription_event` entities and relationships to the Medicare domain.
- Whether provider relationships should be added after implementing optional/blank-safe entity mappings, because CMS provider NPI fields are not complete.
- Whether full CMS uploads should be supported through the existing API upload path or through a streaming/bulk loader; the largest file has over 5.5 million rows and may exceed the configured upload size and memory profile.
