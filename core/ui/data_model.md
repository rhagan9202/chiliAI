# Data Model
**IntegrityAI · Program Integrity Accelerator**
`domain-pack/docs/data_model.md`

---

## Overview

This document defines the entity relationship model, mock data schemas (as used in the demo), and the API contract shapes the production system should implement. It bridges the fields defined in `fields_dictionary.md` into concrete data structures that can be used to hydrate the UI, configure the demo, or design the backend API.

---

## Entity Relationship Diagram

```
Program
  │
  ├──< Provider
  │       │
  │       ├──< AnomalySignal ──────────> PolicyCitation (via PKG query)
  │       │         │                         │
  │       │         └──────────────────> PolicyDetermination
  │       │                                   │
  │       │                            ├──< ComplianceAction
  │       │                            └──> PolicyGap
  │       │
  │       └──< Case
  │               │
  │               ├──> Investigator (assigned to)
  │               └──< ComplianceAction (logged to case)
  │
  └──< PolicyGap
          │
          └──< PolicyCitation (source policy)

Legend:
  ──<  one-to-many
  ──>  many-to-one (foreign key)
```

### Key Relationships

| Relationship | Cardinality | Notes |
|-------------|-------------|-------|
| Program → Provider | 1:N | A provider can exist in multiple programs (same NPI, different program context) |
| Provider → AnomalySignal | 1:N | Multiple signals per provider are the norm for high-risk cases |
| AnomalySignal → PolicyCitation | M:N | One signal queries multiple policies; one policy may apply to multiple signals |
| AnomalySignal → PolicyDetermination | 1:1 | One determination per signal (aggregates all retrieved citations) |
| PolicyDetermination → ComplianceAction | 1:N | Multiple recommended actions per determination |
| PolicyDetermination → PolicyGap | 0:1 | A gap is optional — only raised when the AI detects ambiguity |
| Provider → Case | 1:N | Multiple cases can be opened against a provider over time |
| Case → Investigator | N:1 | One investigator per case at a time (reassignable) |
| PolicyGap → Program | M:N | Gaps can affect one or both programs |

---

## Mock Data Schemas

These are the exact data shapes used in the demo's static data layer. Use these to hydrate the UI in the demo and as a reference contract for backend implementation.

---

### Schema: Program

```javascript
{
  id: 'medicare',                          // string — unique program identifier
  label: 'Medicare FFS',                  // string — display name
  color: '#00d4ff',                        // hex string — UI accent color
  kpis: {
    flagged:    '3,241',                  // string — pre-formatted
    savings:    '$52.7M',
    resolved:   '1,847',
    confidence: '88%'
  },
  trend: [                                // array — 12 monthly data points
    { m: 'Sep', a: 180, s: 3.2 },        // m=month label, a=anomaly count, s=savings $M
    { m: 'Oct', a: 214, s: 3.8 },
    // ...12 entries
  ],
  cats: [                                 // array — recovery by signal category
    { n: 'Billing Pattern', v: 21.3, c: 1204 },  // n=label, v=$M, c=case count
    { n: 'Network Anomaly', v: 16.1, c: 847  },
    { n: 'Trend Shift',     v: 9.8,  c: 623  },
    { n: 'Beneficiary Abuse', v: 5.5, c: 567 },
  ],
  policyCorpus: ['CMS_IOM', 'CMS_PIM', 'OIG_WorkPlan', 'NCCI', 'AMA_CPT'],
  claimsSchema: 'HCPCS'
}
```

---

### Schema: Provider (Feed row)

```javascript
{
  id:    1,                                    // integer — internal ID
  name:  'Advanced Pain Specialists',          // string
  npi:   '1234567890',                         // string(10) — always 10 digits
  type:  'Billing + Trend',                    // string — signal type display label
  risk:  94,                                   // integer 0–100
  conf:  89,                                   // integer 0–100 (confidence %)
  amt:   '$2.1M',                              // string — pre-formatted at-risk amount
  flag:  'UPCODING · HCPCS CONSOLIDATION',    // string — chip display label (ALL CAPS)
  days:  2,                                    // integer — days since detection
  city:  'Miami, FL',                          // string
  spec:  'Pain Management'                     // string — specialty display label
}
```

---

### Schema: AnomalySignal (PKG signal — for Policy Analysis tab)

```javascript
{
  id:           'sig1',                        // string
  signal:       'HCPCS Code Consolidation',   // string — display name
  icon:         TrendingUp,                   // Lucide component reference
  color:        '#ff4040',                    // hex — semantic color for this signal
  anomalyScore: 0.94,                         // float 0–1

  policies: [                                 // array — retrieved PolicyCitation objects
    {
      id:          'P1',
      source:      'CMS IOM Pub. 100-04, Ch. 12 §30.6.1',
      title:       'E&M Documentation Requirements — Level of Service Selection',
      relevance:   97,                        // integer 0–100
      snippet:     'The selection of the appropriate level of E&M service…',
      ruleType:    'Coding Requirement',
    },
    // ...additional citations
  ],

  determination: 'LIKELY VIOLATION',          // string — display label
  determinationConf: 91,                      // integer 0–100

  reasoning: 'Full plain-language reasoning paragraph…',  // string

  actions: [                                  // array — ComplianceAction objects
    {
      type:     'IMMEDIATE',                  // string — type label
      label:    'Prepayment Edit',            // string — action name
      desc:     'Place provider on prepayment review…',   // string
      priority: 'high',                       // 'high' | 'med' | 'low'
    },
    // ...additional actions
  ],

  policyGap: 'IOM §30.6.1 lacks a quantitative threshold…'  // string | null
}
```

---

### Schema: HCPCS Trend Data (Signal 1 chart)

```javascript
// 18 monthly data points
[
  { m: "Mar'23", codes: 47, top3: 38, bill: 42 },
  // m     = period label
  // codes = unique HCPCS code count (decreasing)
  // top3  = top-3 code billing concentration % (increasing)
  // bill  = estimated monthly billing in $K (increasing)
  { m: "Apr'23", codes: 44, top3: 41, bill: 45 },
  { m: "May'23", codes: 41, top3: 45, bill: 49 },
  // ...
  { m: "Aug'24", codes: 6,  top3: 98, bill: 228 },
]
```

---

### Schema: E&M Distribution Data (Signal 2 grouped bar chart)

```javascript
// One object per E&M code level
[
  { code: '99211', prov: 1,  p90: 3,  med: 7  },
  { code: '99212', prov: 2,  p90: 8,  med: 18 },
  { code: '99213', prov: 5,  p90: 22, med: 32 },
  { code: '99214', prov: 14, p90: 42, med: 25 },
  { code: '99215', prov: 78, p90: 25, med: 18 },
  // code = E&M level label
  // prov = this provider's % of E&M claims
  // p90  = 90th percentile peer value
  // med  = peer median value
]
```

---

### Schema: E&M Trend Data (Signal 2 area chart)

```javascript
// 18 monthly data points
[
  { m: "Mar'23", prov: 31, peer: 19 },
  // m    = period label
  // prov = provider's 99215 utilization rate %
  // peer = peer median 99215 utilization rate %
  // ...
  { m: "Aug'24", prov: 78, peer: 18 },
]
```

---

### Schema: Network Nodes (Signal 3 diagram)

```javascript
[
  {
    id:     'aps',
    label:  'Advanced Pain\nSpecialists',   // \n = line break in SVG text
    x:      210,                             // SVG x coordinate
    y:      135,                             // SVG y coordinate
    r:      40,                              // node radius (proportional to risk)
    color:  '#ff4040',
    risk:   94,
    status: 'SUBJECT'                        // 'SUBJECT' | 'FLAGGED'
  },
  {
    id: 'sun', label: 'Sunrise Medical\nGroup',
    x: 345, y: 55, r: 24, color: '#ff4040', risk: 91, status: 'FLAGGED'
  },
  // ...additional nodes
]
```

---

### Schema: Network Edges (Signal 3 diagram)

```javascript
[
  {
    from:    'aps',
    to:      'sun',
    overlap: 34,           // integer — shared patient overlap %
    vol:     287,          // integer — shared patient count
    w:       3.8           // float — SVG stroke-width (visual weight)
  },
  // ...additional edges
]
```

---

### Schema: Network Co-billing Table

```javascript
[
  {
    name:    'Sunrise Medical Group',
    npi:     '9876543210',
    spec:    'Primary Care',
    overlap: 34,           // integer — shared patient %
    vol:     287,          // integer — shared patient count
    risk:    91,           // integer — risk score
    status:  'FLAGGED'     // string
  },
  // ...3 additional rows
]
```

---

### Schema: Case

```javascript
{
  id:       'MC-2024-0891',           // string — formatted case ID
  prov:     'Advanced Pain Specialists',
  type:     'Billing + Trend',        // string — signal type display
  risk:     94,
  status:   'Under Review',           // string — status display label
  analyst:  'J. Morrison',            // string | 'Unassigned'
  amt:      '$1.4M',                  // string | '—'
  date:     'Sep 4'                   // string — short date display
}
```

---

### Schema: PolicyGap

```javascript
{
  id:                'G1',
  severity:          'CRITICAL',                        // 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  title:             'No Quantitative Code Concentration Threshold',
  scope:             'E&M & Procedure Coding',
  affectedProviders: 847,                               // integer
  estimatedExposure: '$124M',                           // string — pre-formatted
  source:            'IOM Pub. 100-04, Ch. 12 §30.6.1',
  description:       'Policy requires E&M codes to reflect documented complexity…',
  recommendation:    'Establish a maximum 85% billing concentration rule…',
  programImpact:     'medicare',                        // 'medicare' | 'medicaid' | 'both'
  casesExposing:     14                                 // integer
}
```

---

### Schema: Policy Trend Data (Policy Intelligence chart)

```javascript
// Quarterly data points
[
  { m: "Q1'23", gaps: 8, cases: 34, exposure: 41 },
  // m        = quarter label
  // gaps     = cumulative identified policy gaps
  // cases    = cases exploiting gaps this quarter
  // exposure = estimated dollar exposure $M
  { m: "Q2'23", gaps: 9,  cases: 41, exposure: 49 },
  // ...8 quarters
  { m: "Q4'24", gaps: 14, cases: 91, exposure: 114 },
]
```

---

### Schema: Investigator (Queue Health)

```javascript
{
  name:    'J. Morrison',
  active:  8,              // integer — active cases
  pending: 3,              // integer — pending cases
  closed:  24,             // integer — closed this quarter
  load:    73              // integer 0–100 — capacity utilization %
}
// Special Unassigned slot: { name: 'Unassigned', active: 0, pending: 12, closed: 0, load: 0 }
```

---

## API Contract Shapes (Production)

These are the recommended REST/JSON API response shapes the production backend should implement to hydrate each screen. The demo uses static mock data in place of these endpoints.

---

### GET `/api/programs`

Returns all configured programs for the switcher.

```typescript
Response: Program[]

Program {
  id:           string
  label:        string
  color:        string          // hex
  claimsSchema: 'HCPCS' | 'CPT' | 'NDC'
  policyCorpus: string[]
}
```

---

### GET `/api/dashboard?program={id}&period={quarter|ytd|custom}`

Returns KPI summary, trend data, category breakdown, and queue health for the Dashboard.

```typescript
Response: {
  kpis: {
    flaggedProviders: number
    potentialRecovery: number    // raw number in dollars
    casesResolved:    number
    avgConfidence:    number     // 0–100
    periodLabel:      string
    qoqChangePct: {
      flaggedProviders: number
      potentialRecovery: number
      casesResolved: number
    }
  }
  trend: TrendPoint[]           // monthly/quarterly time series
  categories: CategoryBreakdown[]
  queue: InvestigatorQueueItem[]
}

TrendPoint {
  period:         string        // display label
  anomalyCount:   number
  estimatedSavings: number      // $M
}

CategoryBreakdown {
  signalType:     string
  recovery:       number        // $M
  caseCount:      number
}

InvestigatorQueueItem {
  investigatorId: string
  name:           string
  activeCases:    number
  pendingCases:   number
  closedCases:    number
  maxCases:       number        // denominator for capacity %
}
```

---

### GET `/api/feed?program={id}&type={signalType}&page={n}&pageSize={n}`

Returns paginated anomaly detection feed, sorted by risk score descending.

```typescript
Response: {
  total:    number
  page:     number
  pageSize: number
  results:  FeedItem[]
}

FeedItem {
  providerId:        string
  providerName:      string
  npi:               string
  signalType:        string        // display label
  signalSubtype:     string
  riskScore:         number        // 0–100
  confidenceLevel:   number        // 0–100
  atRisk:            number        // dollars
  flagLabel:         string        // ALL CAPS chip label
  daysSinceDetection: number
  city:              string
  specialty:         string
  inlineReasoning:   string        // short paragraph for expanded row
}
```

---

### GET `/api/provider/{npi}?program={id}`

Returns full provider dossier for the Provider Deep-Dive screen.

```typescript
Response: {
  provider: {
    npi:              string
    name:             string
    specialty:        string
    city:             string
    state:            string
    enrollmentStatus: string
    peerCohortId:     string
    peerCohortSize:   number
  }
  signals: SignalSummary[]
  chartData: {
    hcpcsTrend:    HCPCSTrendPoint[]
    emDistribution: EMDistPoint[]
    emTrend:       EMTrendPoint[]
    billingTimeline: BillingPoint[]
    network: {
      nodes: NetworkNode[]
      edges: NetworkEdge[]
      table: NetworkTableRow[]
    }
  }
  evidenceLog: EvidenceEvent[]
}

SignalSummary {
  id:             string
  type:           string
  subtype:        string
  riskScore:      number
  confidenceLevel: number
  atRisk:         number
  flagLabel:      string
  description:    string    // plain-language summary for the signal banner
}
```

---

### GET `/api/provider/{npi}/policy?program={id}`

Returns PKG analysis results for the Policy Analysis tab. This endpoint may have higher latency (PKG query + LLM call). Implement with loading state in UI.

```typescript
Response: {
  pkgVersion:     string
  corpusSize:     number
  queriedAt:      string      // ISO datetime
  signals: PolicySignalResult[]
}

PolicySignalResult {
  signalId:          string
  signalName:        string
  anomalyScore:      number   // 0–1
  citations: PolicyCitation[]
  determination: {
    verdict:           'likely_violation' | 'possible_violation' | 'corner_case' | 'no_violation'
    verdictLabel:      string       // display string
    confidence:        number       // 0–100
    reasoningChain:    string       // full plain-language reasoning
    reasoningSteps:    string[]     // step labels for StepChain component
    citationIds:       string[]     // IDs of grounding citations
  }
  actions: ComplianceAction[]
  policyGap: string | null
}

PolicyCitation {
  id:            string
  source:        string
  title:         string
  ruleType:      string
  relevanceScore: number      // 0–100
  snippet:       string       // max 300 chars
  documentUrl:   string | null
  effectiveDate: string | null  // ISO date
}

ComplianceAction {
  type:        string    // 'IMMEDIATE' | 'INVESTIGATION' | 'COMPLIANCE'
  label:       string
  description: string
  priority:    'high' | 'med' | 'low'
}
```

---

### GET `/api/cases?program={id}&status={status}&analyst={id}&page={n}`

Returns paginated case management list.

```typescript
Response: {
  total:       number
  summary: {   // counts by status for the summary row
    pending:          number
    underReview:      number
    escalated:        number
    closedConfirmed:  number
    closedCleared:    number
  }
  cases: CaseListItem[]
}

CaseListItem {
  caseId:       string
  providerName: string
  npi:          string
  signalType:   string
  riskScore:    number
  status:       string      // status display label
  analystName:  string | null
  atRisk:       number | null
  openedDate:   string      // ISO date
}
```

---

### GET `/api/policy-intelligence?program={id}`

Returns Policy Intelligence screen data for CMS leadership.

```typescript
Response: {
  kpis: {
    gapsIdentified:        number
    totalEstimatedExposure: number    // dollars
    casesExposingGaps:     number
    recommendationCount:   number
    programsImpacted:      string
  }
  trend: PolicyTrendPoint[]
  gaps: PolicyGap[]
}

PolicyTrendPoint {
  period:       string        // quarter label
  gapsCount:    number
  cases:        number
  exposure:     number        // $M
}

PolicyGap {
  id:                string
  severity:          'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  title:             string
  scope:             string
  source:            string
  description:       string
  recommendation:    string
  programImpact:     'medicare' | 'medicaid' | 'both'
  affectedProviders: number
  estimatedExposure: number   // dollars (raw)
  casesExposing:     number
}
```

---

## Data Formatting Conventions

The UI renders pre-formatted strings for display values in the demo (e.g., `"$52.7M"`, `"3,241"`). In production, the API should return raw numbers and let the frontend format them using these conventions:

| Value Type | Format | Example |
|-----------|--------|---------|
| Dollar amounts ≥ $1B | `$X.XB` | `$1.2B` |
| Dollar amounts ≥ $1M | `$X.XM` | `$52.7M` |
| Dollar amounts ≥ $1K | `$XK` | `$847K` |
| Dollar amounts < $1K | `$X` | `$340` |
| Integer counts | Locale string | `3,241` |
| Percentages | `X%` | `88%` |
| Confidence (0–1) | `Math.round(val * 100)` → `X%` | `89%` |
| Risk score | Integer, no formatting | `94` |
| Dates (short) | `MMM DD` | `Sep 4` |
| Dates (long) | `MMM DD, YYYY` | `Aug 28, 2024` |
| Period labels (monthly) | `"Mon'YY"` | `"Mar'23"` |
| Period labels (quarterly) | `"QN'YY"` | `"Q1'23"` |

---

## State Management Architecture

The demo manages all state via React `useState` hooks in the root `App` component, with these global state variables:

| State Variable | Type | Description | Set By |
|----------------|------|-------------|--------|
| `screen` | `string` | Active screen ID | Nav button clicks |
| `prog` | `string` | Active program ID (`'medicare'` \| `'medicaid'`) | Program switcher |
| `aiOpen` | `boolean` | AI panel visibility | AI toggle button |
| `selProv` | `Provider \| null` | Provider selected for deep-dive | Feed "Review" click |

Local state per component:

| Component | State | Description |
|-----------|-------|-------------|
| `AnomalyFeed` | `expanded`, `filter` | Which row is expanded; active type filter |
| `ProviderDive` | `tab` | Active tab ID |
| `PolicyIntel` | `selGap` | Which gap card is expanded |
| `AIPanel` | `msgs`, `input` | Message thread; current input value |
| `CaseMgmt` | (none in demo) | — |

**Production architecture recommendation:** Replace root `useState` with a context provider or lightweight state manager (Zustand / Jotai) to support:
- Cross-component program context subscription
- Deep-link URL synchronization (screen + tab + selected provider)
- Persistent user preferences (last active program, panel state)
