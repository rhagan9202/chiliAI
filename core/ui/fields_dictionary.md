# Fields Dictionary
**IntegrityAI · Program Integrity Accelerator**
`domain-pack/docs/fields_dictionary.md`

---

## Overview

This dictionary defines every data field surfaced in the IntegrityAI UI. Fields are organized by **domain entity** — the logical object they describe — and each entry notes which screens consume the field, whether it is program-specific, and how it should be configured when adapting to a new domain pack.

### Conventions

| Symbol | Meaning |
|--------|---------|
| 🔒 | Core field — present in all domain packs, value may vary |
| 🔧 | Configurable field — label, logic, or source varies by domain pack |
| ➕ | Extension point — field may not exist in all programs; add when applicable |
| `[PROGRAM]` | Placeholder — replace with program-specific value at configuration time |

### Domain Pack Dimensions Covered

A **domain pack** is the configuration layer that adapts the accelerator to a specific program. The fields in this dictionary vary across six dimensions:

1. **Program type** (Medicare FFS, Medicaid FFS, CHIP, etc.)
2. **Anomaly signal types** and their detection metadata
3. **Policy corpus** and knowledge graph sources
4. **UI terminology and field labels**
5. **User roles and permissions**
6. **Claims data schema and code systems** (HCPCS, ICD, NDC, etc.)

---

## Entity: Program

The top-level context object. Drives the program switcher, color theming, and data segmentation across all screens.

| Field | Type | Description | Domain Pack Notes | Screens |
|-------|------|-------------|-------------------|---------|
| `program.id` 🔒 | `string` | Unique identifier for the program. | `medicare_ffs`, `medicaid_ffs`. Extend with `chip`, `part_d`, `mapd`, etc. | All |
| `program.label` 🔒 | `string` | Display name shown in UI headers and badges. | e.g., "Medicare FFS", "Medicaid FFS". Configure per pack. | All |
| `program.color` 🔒 | `hex string` | Primary accent color for this program's UI theme. | Medicare: `#00d4ff` (cyan). Medicaid: `#a855f7` (purple). Assign a distinct color per program. | All |
| `program.claimsSchema` 🔧 | `enum` | Coding system used for procedure codes. | `HCPCS` for Medicare/Medicaid FFS. `NDC` for Part D. `CPT` for commercial packs. | Provider Deep-Dive, Feed |
| `program.policyCorpus` 🔧 | `string[]` | List of policy source identifiers indexed in the PKG for this program. | Medicare: `["CMS_IOM", "CMS_PIM", "OIG_WorkPlan", "NCCI", "AMA_CPT"]`. Medicaid: add `["State_Plan_Amendments", "CMS_CMCS_Guidance"]`. | Policy Analysis tab, Policy Intelligence |
| `program.mac` ➕ | `string` | Medicare Administrative Contractor jurisdiction (Medicare FFS only). | Only relevant for Medicare FFS. Omit for Medicaid. | Dashboard, Provider Deep-Dive |
| `program.statePlan` ➕ | `string` | State Medicaid Plan identifier (Medicaid FFS only). | Only relevant for Medicaid. Omit for Medicare. | Dashboard, Provider Deep-Dive |

---

## Entity: Provider

A healthcare entity — individual practitioner, group practice, facility, or supplier — identified by NPI.

| Field | Type | Description | Domain Pack Notes | Screens |
|-------|------|-------------|-------------------|---------|
| `provider.npi` 🔒 | `string(10)` | National Provider Identifier. 10-digit CMS-assigned unique ID. | Universal across Medicare and Medicaid FFS. Not applicable to Part D (use DEA/NPI hybrid). | Feed, Provider Deep-Dive, Case Management |
| `provider.name` 🔒 | `string` | Legal name of the provider or organization. | Source from NPPES registry. | All |
| `provider.type` 🔒 | `enum` | Entity type classification. | `individual`, `group`, `facility`, `supplier`, `pharmacy`. Drives peer cohort selection logic. | Feed, Provider Deep-Dive |
| `provider.specialty` 🔧 | `string` | Primary CMS specialty code and label. | Medicare: uses CMS specialty codes 01–89. Medicaid: may use state-specific taxonomy codes. Configure taxonomy mapping per pack. | Feed, Provider Deep-Dive |
| `provider.city` 🔒 | `string` | Practice city from NPPES enrollment record. | — | Feed, Provider Deep-Dive |
| `provider.state` 🔒 | `string(2)` | Practice state abbreviation. | Drives peer cohort geographic filtering. | Feed, Provider Deep-Dive |
| `provider.mac` ➕ | `string` | Medicare Administrative Contractor serving this provider's jurisdiction. | Medicare FFS only. | Provider Deep-Dive |
| `provider.enrollmentStatus` 🔒 | `enum` | Active enrollment status in the program. | `active`, `revoked`, `suspended`, `excluded`. Drives alert badges. | Provider Deep-Dive |
| `provider.peerCohortId` 🔧 | `string` | Identifier of the AI-assigned peer comparison cohort. | Cohort definition (specialty × geography × volume tier) is configurable per domain pack. | Provider Deep-Dive |
| `provider.peerCohortSize` 🔒 | `integer` | Number of providers in the assigned peer cohort. | Displayed as `n=847` in peer comparison charts. | Provider Deep-Dive |

---

## Entity: AnomalySignal

A single detected anomaly pattern linked to a provider or claim. Multiple signals may be associated with one provider.

| Field | Type | Description | Domain Pack Notes | Screens |
|-------|------|-------------|-------------------|---------|
| `signal.id` 🔒 | `string` | Unique signal identifier. | System-generated. | Feed, Provider Deep-Dive |
| `signal.type` 🔧 | `enum` | Anomaly category. | Configure valid types per domain pack. Core types: `billing_pattern`, `network`, `trend_shift`, `beneficiary_abuse`. Add program-specific types (e.g., `pharmacy_dispensing` for Part D). | Feed, Provider Deep-Dive |
| `signal.subtype` 🔧 | `string` | Specific anomaly pattern within a type. | Examples: `upcoding`, `unbundling`, `hcpcs_consolidation`, `referral_ring`, `impossible_day`. Map to domain-specific patterns per pack. | Feed, Provider Deep-Dive |
| `signal.flag` 🔒 | `string` | Short human-readable label displayed in the UI as a chip. | e.g., `UPCODING · HCPCS CONSOLIDATION`. Configurable per signal subtype. | Feed, Provider Deep-Dive |
| `signal.riskScore` 🔒 | `integer (0–100)` | Composite AI risk score. Higher = greater anomaly severity. | Threshold bands are configurable: default `HIGH ≥ 90`, `MED ≥ 75`, `LOW < 75`. Adjust per program risk tolerance. | Feed, Provider Deep-Dive, Case Management |
| `signal.confidenceLevel` 🔒 | `float (0–1)` | Model confidence in the signal detection. Displayed as percentage. | Confidence threshold for surfacing to analysts is configurable. Default: surface if `confidence ≥ 0.70`. | Feed, Provider Deep-Dive |
| `signal.atRisk` 🔒 | `currency string` | Estimated dollar amount at risk for this signal. | Derived from claims data × peer-adjusted expected billing. Calculation method may differ by program. | Feed, Provider Deep-Dive, Case Management |
| `signal.detectedAt` 🔒 | `ISO 8601 datetime` | Timestamp when the AI model first detected the signal. | — | Feed, Provider Deep-Dive |
| `signal.daysSinceDetection` 🔒 | `integer` | Days elapsed since detection. Derived from `detectedAt`. | Used for aging/urgency indicators in the feed. | Feed |
| `signal.codes` 🔧 | `string[]` | Procedure or diagnosis codes associated with the signal. | For HCPCS/CPT-based signals. Replace with `NDC` codes for Part D. | Provider Deep-Dive |
| `signal.peerPercentile` 🔧 | `float (0–100)` | Provider's percentile rank within peer cohort for the primary metric. | Displayed as "Top 1.3% nationally." Configure peer metric per signal type. | Provider Deep-Dive |
| `signal.trendData` 🔧 | `object[]` | Time-series data supporting the signal visualization. | Schema varies by signal type. See `SignalTrendPoint` schema below. | Provider Deep-Dive — Overview tab |

### Sub-schema: SignalTrendPoint

| Field | Type | Description |
|-------|------|-------------|
| `period` | `string` | Display label for the time period (e.g., `"Mar'23"`). |
| `providerValue` | `float` | Provider's metric value for this period. |
| `peerMedian` | `float` | Peer cohort median for the same period. |
| `peer90thPct` | `float` | 90th percentile peer value for the same period. |
| `anomalyFlag` | `boolean` | Whether this period was individually flagged as anomalous. |

---

## Entity: PolicyCitation

A policy document section retrieved from the Policy Knowledge Graph (PKG) in response to an anomaly signal query.

| Field | Type | Description | Domain Pack Notes | Screens |
|-------|------|-------------|-------------------|---------|
| `citation.id` 🔒 | `string` | Unique citation identifier within the PKG. | — | Provider Deep-Dive — Policy tab |
| `citation.source` 🔒 | `string` | Formal citation string for the source document. | e.g., `CMS IOM Pub. 100-04, Ch. 12 §30.6.1`. Format per program's citation standard. | Provider Deep-Dive — Policy tab, Policy Intelligence |
| `citation.title` 🔒 | `string` | Title of the retrieved policy section. | — | Provider Deep-Dive — Policy tab |
| `citation.ruleType` 🔧 | `enum` | Classification of the policy instrument. | Core types: `coding_requirement`, `billing_integrity`, `program_integrity`, `federal_statute`, `regulatory`, `oig_priority`, `coding_standard`. Extend per program corpus. | Provider Deep-Dive — Policy tab |
| `citation.relevanceScore` 🔒 | `integer (0–100)` | PKG retrieval relevance score for this citation relative to the query signal. | Drives ranking and display order. Configurable retrieval threshold (default: surface if `relevance ≥ 70`). | Provider Deep-Dive — Policy tab |
| `citation.snippet` 🔒 | `string` | Extracted verbatim text passage from the policy document. | Max display length: 300 characters. Truncate with ellipsis. | Provider Deep-Dive — Policy tab |
| `citation.documentUrl` ➕ | `string` | Link to the full source document. | Include when the policy document is publicly accessible (e.g., CMS.gov, eCFR.gov). | Provider Deep-Dive — Policy tab |
| `citation.effectiveDate` ➕ | `ISO 8601 date` | Effective date of the cited policy version. | Important for enforcement validity — a policy must have been in effect during the claim period. | Provider Deep-Dive — Policy tab |

---

## Entity: PolicyDetermination

The AI-generated assessment of whether a flagged anomaly signal constitutes a policy violation, produced by grounding the signal against retrieved policy citations.

| Field | Type | Description | Domain Pack Notes | Screens |
|-------|------|-------------|-------------------|---------|
| `determination.signalId` 🔒 | `string` | Reference to the parent `AnomalySignal`. | — | Provider Deep-Dive — Policy tab |
| `determination.verdict` 🔒 | `enum` | AI determination outcome. | Values: `likely_violation`, `possible_violation`, `corner_case`, `no_violation`. Labels and color mapping configurable per pack. | Provider Deep-Dive — Policy tab |
| `determination.confidence` 🔒 | `float (0–1)` | Model confidence in the determination. | Displayed as a percentage. Low confidence (<70%) should surface a "Further Review Required" qualifier. | Provider Deep-Dive — Policy tab |
| `determination.reasoningChain` 🔒 | `string` | Plain-language narrative explaining the AI's reasoning, grounded in retrieved citations. | Auditable text field. Should reference specific policy sources by citation ID. | Provider Deep-Dive — Policy tab |
| `determination.citationIds` 🔒 | `string[]` | IDs of `PolicyCitation` records used as grounding evidence. | — | Provider Deep-Dive — Policy tab |
| `determination.policyGap` ➕ | `string` | If detected, a plain-language description of an ambiguity or gap in the cited policy that complicates enforcement. | Feeds into `PolicyGap` entity for the Policy Intelligence screen. | Provider Deep-Dive — Policy tab, Policy Intelligence |

---

## Entity: ComplianceAction

A recommended investigative or compliance step generated from a policy determination.

| Field | Type | Description | Domain Pack Notes | Screens |
|-------|------|-------------|-------------------|---------|
| `action.id` 🔒 | `string` | Unique action identifier. | — | Provider Deep-Dive — Policy tab, Case Management |
| `action.type` 🔧 | `enum` | Action category. | Core types: `immediate`, `investigation`, `compliance`. Extend with `referral`, `prepayment_edit`, `exclusion` per program. | Provider Deep-Dive — Policy tab |
| `action.label` 🔧 | `string` | Short action name displayed as a header. | e.g., "Prepayment Edit", "Records Request". Configure terminology per program. CMS uses "Additional Documentation Request (ADR)" not "Records Request." | Provider Deep-Dive — Policy tab |
| `action.description` 🔒 | `string` | Full plain-language description of the recommended action. | — | Provider Deep-Dive — Policy tab |
| `action.priority` 🔒 | `enum` | Urgency level. | `high`, `medium`, `low`. Drives color coding: `high` = red, `medium` = amber, `low` = cyan. | Provider Deep-Dive — Policy tab |
| `action.caseId` ➕ | `string` | Case ID if this action has been logged to Case Management. | Populated after analyst assigns action to a case. | Case Management |

---

## Entity: PolicyGap

A systemic gap, ambiguity, or weakness in CMS policy or oversight rules identified through cross-case pattern analysis. Surfaces in the Policy Intelligence screen for CMS leadership.

| Field | Type | Description | Domain Pack Notes | Screens |
|-------|------|-------------|-------------------|---------|
| `gap.id` 🔒 | `string` | Unique gap identifier. | — | Policy Intelligence |
| `gap.title` 🔒 | `string` | Short descriptive title of the gap. | — | Policy Intelligence |
| `gap.severity` 🔒 | `enum` | Impact severity classification. | `critical`, `high`, `medium`, `low`. Drives alert coloring and sort order. | Policy Intelligence |
| `gap.scope` 🔧 | `string` | Policy or functional area where the gap exists. | e.g., "E&M & Procedure Coding", "Statistical Aberrant Billing". Configure per program's policy landscape. | Policy Intelligence |
| `gap.source` 🔒 | `string` | Primary policy citation where the gap originates. | References `citation.source` format. | Policy Intelligence |
| `gap.description` 🔒 | `string` | Plain-language description of the gap and its enforcement implications. | — | Policy Intelligence |
| `gap.recommendation` 🔒 | `string` | Specific, actionable policy change or oversight measure recommended to close the gap. | — | Policy Intelligence |
| `gap.programImpact` 🔒 | `enum` | Which programs are affected. | `medicare`, `medicaid`, `both`. Used for program-filter display logic. | Policy Intelligence |
| `gap.affectedProviders` 🔒 | `integer` | Estimated number of providers whose behavior is enabled by this gap. | — | Policy Intelligence |
| `gap.estimatedExposure` 🔒 | `currency string` | Estimated total dollar exposure attributable to this gap across the program. | — | Policy Intelligence |
| `gap.casesExposing` 🔒 | `integer` | Count of active or historical cases that demonstrate this gap. | Used for gap severity matrix chart. | Policy Intelligence |

---

## Entity: Case

An investigative case record created when an analyst escalates a provider or claim anomaly for formal review.

| Field | Type | Description | Domain Pack Notes | Screens |
|-------|------|-------------|-------------------|---------|
| `case.id` 🔒 | `string` | Unique case identifier. | Format: `[PROGRAM_PREFIX]-[YEAR]-[SEQUENCE]`. e.g., `MC-2024-0891` for Medicare. Configure prefix per program. | Case Management |
| `case.providerId` 🔒 | `string` | NPI of the subject provider. | — | Case Management |
| `case.providerName` 🔒 | `string` | Display name of the subject provider. | — | Case Management |
| `case.signalType` 🔒 | `string` | Primary anomaly signal type driving the case. | Derived from `signal.type + signal.subtype`. | Case Management |
| `case.riskScore` 🔒 | `integer (0–100)` | Risk score at time of case creation. | Inherited from `signal.riskScore`. May be updated as investigation progresses. | Case Management |
| `case.status` 🔧 | `enum` | Current case lifecycle status. | Core statuses: `pending`, `under_review`, `escalated`, `closed_confirmed`, `closed_cleared`. Extend with program-specific statuses (e.g., `referred_doj`, `prepayment_hold`). | Case Management |
| `case.analyst` 🔒 | `string` | Full name of the assigned investigator. | `null` displays as "Unassigned" with amber coloring. | Case Management |
| `case.atRisk` 🔒 | `currency string` | Dollar amount under investigation. | `—` if not yet quantified. | Case Management |
| `case.openedDate` 🔒 | `ISO 8601 date` | Date the case was formally opened. | Displayed in short format `MMM DD` in the case table. | Case Management |
| `case.actions` ➕ | `ComplianceAction[]` | Actions logged against this case. | Populated from Policy tab recommendations promoted to the case. | Case Management |
| `case.notes` ➕ | `string` | Free-text investigator notes. | Append-only audit trail. | Case Management |

---

## Entity: KPISummary

Aggregated program-level metrics displayed on the Executive Dashboard.

| Field | Type | Description | Domain Pack Notes | Screens |
|-------|------|-------------|-------------------|---------|
| `kpi.flaggedProviders` 🔒 | `string` | Count of providers with active anomaly signals this quarter. | Format: locale string with comma separator. | Dashboard |
| `kpi.potentialRecovery` 🔒 | `currency string` | Sum of `signal.atRisk` across all active signals. | Display in $M or $B depending on program scale. Configure abbreviation threshold. | Dashboard |
| `kpi.casesResolved` 🔒 | `string` | Count of cases closed this quarter (both confirmed and cleared). | — | Dashboard |
| `kpi.avgConfidence` 🔒 | `string` | Average AI confidence level across all active detections. | Displayed as percentage. | Dashboard |
| `kpi.period` 🔒 | `string` | The reporting period label. | e.g., "This Quarter", "FY2024 YTD". Configure per program reporting cadence. | Dashboard |

---

## Entity: Investigator

A program integrity staff member. Used for queue health display and case assignment.

| Field | Type | Description | Domain Pack Notes | Screens |
|-------|------|-------------|-------------------|---------|
| `investigator.id` 🔒 | `string` | Unique user identifier. | Sourced from identity provider / SSO. | Case Management, Dashboard |
| `investigator.name` 🔒 | `string` | Full display name. | — | Case Management, Dashboard |
| `investigator.initials` 🔒 | `string(2)` | Two-letter initials for avatar display. | Derived from name. | Top navigation bar |
| `investigator.role` 🔧 | `enum` | User role governing screen access. | Core roles: `analyst`, `supervisor`, `cms_leader`. Map to program-specific role taxonomy. See `navigation_flow.md` for role-gated screens. | All |
| `investigator.activeCases` 🔒 | `integer` | Count of cases currently assigned with status `under_review` or `escalated`. | — | Dashboard — Queue Health |
| `investigator.pendingCases` 🔒 | `integer` | Count of cases assigned but not yet started (`pending`). | — | Dashboard — Queue Health |
| `investigator.closedCases` 🔒 | `integer` | Count of cases closed by this investigator this quarter. | — | Dashboard — Queue Health |
| `investigator.capacityPct` 🔒 | `integer (0–100)` | Derived workload capacity utilization percentage. | Calculation: `(activeCases / maxCases) * 100`. `maxCases` is configurable per program. Color thresholds: `≥80` red, `≥60` amber, `<60` green. | Dashboard — Queue Health |

---

## Screen Cross-Reference Index

Quick lookup: which entities appear on which screens.

| Screen | Primary Entities | Secondary Entities |
|--------|------------------|--------------------|
| Dashboard | `KPISummary`, `Investigator` | `Program` |
| Anomaly Feed | `AnomalySignal`, `Provider` | `Program` |
| Provider Deep-Dive — Overview | `Provider`, `AnomalySignal` | `Program` |
| Provider Deep-Dive — Policy Analysis | `PolicyCitation`, `PolicyDetermination`, `ComplianceAction` | `AnomalySignal`, `Provider` |
| Provider Deep-Dive — Evidence Log | `AnomalySignal`, `Case` | `Provider` |
| Provider Deep-Dive — Billing Timeline | `AnomalySignal` | `Provider` |
| Case Management | `Case`, `Investigator` | `Provider`, `AnomalySignal` |
| Policy Intelligence | `PolicyGap` | `Program`, `PolicyCitation` |
| AI Investigator Panel | All entities (contextual) | — |

---

## Domain Pack Configuration Checklist

When adapting this accelerator to a new program, review the following field-level configuration points:

- [ ] Set `program.id`, `program.label`, `program.color` for each supported program
- [ ] Define `program.claimsSchema` and configure code system lookups accordingly
- [ ] Populate `program.policyCorpus` with the indexed knowledge graph sources for the program
- [ ] Map `signal.type` and `signal.subtype` enums to program-specific anomaly patterns
- [ ] Configure `signal.riskScore` threshold bands to match program risk tolerance
- [ ] Define `provider.specialty` taxonomy mapping (CMS codes vs. state taxonomy codes)
- [ ] Set `provider.peerCohortId` cohort definition logic (specialty × geography × volume)
- [ ] Extend `action.type` and `action.label` with program-specific investigation actions
- [ ] Add `case.id` prefix per program convention
- [ ] Extend `case.status` with program-specific lifecycle states
- [ ] Configure `investigator.role` mapping to program's organizational role taxonomy
- [ ] Set `investigator.capacityPct` `maxCases` denominator per program staffing model
- [ ] Add any `➕` extension fields required for the program (e.g., `provider.mac`, `provider.statePlan`)
