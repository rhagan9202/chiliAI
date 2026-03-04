# Screen Specifications
**IntegrityAI · Program Integrity Accelerator**
`domain-pack/docs/screens_specs.md`

---

## Overview

This document specifies each screen in the IntegrityAI UI at the component and interaction level — covering layout, component inventory, data bindings, UI states, and domain pack configuration points. It does not contain implementation code; for field-level definitions see `fields_dictionary.md`, and for navigation rules see `navigation_flow.md`.

### Notation

- **`{field}`** — A bound data field. Resolves to the corresponding entity field defined in `fields_dictionary.md`.
- **`[CONFIGURABLE]`** — A value or label that must be set in the domain pack configuration.
- **STATE: X** — A named UI state the component can be in.

---

## Shared Shell Components

These components are present on every screen and are not repeated in per-screen specs.

---

### SH-01 · Sidebar Navigation

**Layout:** Fixed left column, 220px wide. Always visible.

**Sections (top to bottom):**

1. **Logo Block**
   - Product wordmark: `IntegrityAI` — `[CONFIGURABLE: product name]`
   - Subline: `Program Integrity Platform` — `[CONFIGURABLE: platform tagline]`
   - Accent icon: Shield icon, colored with active program color

2. **Program Switcher**
   - Label: `PROGRAM`
   - Toggle button group: one button per configured program
   - STATE: `active` — button fills with `program.color`, label in black
   - STATE: `inactive` — transparent background, muted text
   - Switching programs triggers a global data context refresh

3. **Navigation Items**
   - One button per screen in the screen inventory
   - STATE: `active` — left border accent in `program.color`, background tint, label in `program.color`
   - STATE: `inactive` — no border, no background, dimmed text
   - Items with the `badge` flag render a `PKG` pill in green alongside the label
   - Domain pack note: register or remove nav items by modifying the nav config array — no component code changes required

4. **AI Investigator Toggle** (bottom, above footer)
   - Button: "AI Investigator" with Bot icon
   - STATE: `inactive` — muted border, subtle background
   - STATE: `active` — cyan border, cyan text, pulsing dot indicator (CSS animation: `pkgPulse`)

---

### SH-02 · Top Navigation Bar

**Layout:** Fixed top bar, 54px tall. Spans main content area (not sidebar).

**Components (left to right):**

1. **Global Search Input**
   - Placeholder: `Search providers, NPIs, cases…` — `[CONFIGURABLE]`
   - Width: 300px
   - Behavior: On keystroke, queries providers by name and NPI, cases by ID. Results surface as a dropdown (not yet detailed in this spec; extend in domain pack).

2. **Program Context Badge** (right-aligned)
   - Displays active `program.label` in the program's accent color

3. **Notifications Bell**
   - Icon with red dot indicator when unread notifications exist
   - Behavior: Click opens notification drawer (extend in domain pack)

4. **User Avatar**
   - Circle displaying `investigator.initials`
   - Colored with active `program.color`

---

### SH-03 · AI Investigator Panel

**Layout:** Overlay panel, slides in from the right edge. 420px wide. Full viewport height. Does not affect sidebar or top bar.

**Components (top to bottom):**

1. **Panel Header**
   - Bot icon + "AI Investigator" label
   - Active context indicator: `● ACTIVE · {provider.name}` or generic state when no provider context
   - Close button (X): dismisses panel, restores main content margin

2. **Suggested Prompts Bar**
   - 3 contextual prompt chips, configurable per screen context
   - Default prompts for Provider Deep-Dive context: "What codes are involved?", "Compare to peers", "Recommend next steps" — `[CONFIGURABLE per signal type]`
   - Clicking a prompt populates the input field

3. **Message Thread**
   - Scrollable message list
   - User messages: right-aligned, cyan-tinted bubble
   - Assistant messages: left-aligned, with Bot avatar, standard card background
   - Text is `white-space: pre-wrap` to render line breaks and bullet lists

4. **Input Row**
   - Text input: `Ask about this provider…` placeholder — `[CONFIGURABLE]`
   - Send button: Enter key or click
   - On send: user message appends immediately; assistant response appends after API call resolves

**UI States:**

| State | Description |
|-------|-------------|
| `closed` | Panel hidden; sidebar toggle shows inactive |
| `open-no-context` | Panel open, no provider loaded; generic welcome message |
| `open-with-context` | Panel open, provider NPI and top signal pre-loaded; opening message is signal summary |
| `loading` | Waiting for AI response; typing indicator shown |

**Domain Pack Note:** The AI panel's system prompt and pre-load message template are configurable. Inject `program.label`, `signal.type`, and `provider.specialty` into the prompt template at runtime for program-specific grounding.

---

## Screen: Dashboard

**Route:** `/dashboard`
**Roles:** Analyst (read), Supervisor (read + queue actions)
**Purpose:** Program-level health overview for supervisors and analysts. Entry point for supervisors.

---

### DS-01 · KPI Cards Row

**Layout:** 4 cards in a horizontal flex row. Equal width.

| Card | Bound Field | Accent Color | Trend Indicator |
|------|-------------|--------------|-----------------|
| Flagged Providers | `kpi.flaggedProviders` | Red | QoQ change — `[CONFIGURABLE: comparison period]` |
| Potential Recovery | `kpi.potentialRecovery` | Green | QoQ change |
| Cases Resolved | `kpi.casesResolved` | `program.color` | QoQ change |
| Avg AI Confidence | `kpi.avgConfidence` | Amber | None |

**Each card contains:**
- Top accent line gradient in card color
- Icon in a tinted icon box
- Large value display (`Oxanium` font, 26px bold)
- Label and sub-label
- Optional trend indicator with up arrow and percentage

**Domain Pack Note:** Add, remove, or relabel KPI cards by modifying the KPI config array. The card component accepts any `{icon, label, value, sub, color, trend}` shape.

---

### DS-02 · Anomaly Detection Trend Chart

**Layout:** Left 2/3 of a two-panel row.

**Chart type:** Area chart, dual-series.

**Series:**
- `kpi trend` over 12 months: flagged provider count (left Y-axis)
- `kpi savings` over 12 months: potential recovery in $M (right Y-axis)

**Configuration:**
- X-axis: monthly labels, `[CONFIGURABLE: period length and granularity]`
- Colors: Series 1 = `program.color`; Series 2 = green
- Gradient fill under each line

**Domain Pack Note:** The trend dataset schema requires `{ period, anomalyCount, estimatedSavings }` per time point. Adjust the display period (quarterly vs. monthly) by changing the aggregation in the data layer.

---

### DS-03 · Recovery by Category Chart

**Layout:** Right 1/3 of the same row as DS-02.

**Chart type:** Horizontal bar chart.

**Data:** One bar per `signal.type` showing estimated recovery in $M.

**Domain Pack Note:** Bar categories are derived from the active `signal.type` enum values for the program. Adding a new signal type to the domain pack automatically adds a bar if the chart data includes it.

---

### DS-04 · Investigator Queue Health

**Layout:** Full-width card below the chart row.

**Content:** One mini-card per investigator with:
- Investigator name
- Three stat blocks: `investigator.activeCases` (cyan), `investigator.pendingCases` (amber), `investigator.closedCases` (green)
- Capacity bar: fills red if `≥80%`, amber if `≥60%`, green if `<60%`
- "Unassigned" card last — shows pending case count with no capacity bar

**UI States:**

| State | Trigger | Behavior |
|-------|---------|----------|
| `normal` | `capacityPct < 80` | Green capacity bar |
| `warning` | `60 ≤ capacityPct < 80` | Amber capacity bar |
| `overloaded` | `capacityPct ≥ 80` | Red capacity bar; supervisor sees an action to reassign |
| `unassigned` | Card is the Unassigned slot | No capacity bar; pending count shown in amber |

---

## Screen: Anomaly Feed

**Route:** `/feed`
**Roles:** Analyst, Supervisor
**Purpose:** Prioritized list of all active anomaly signals, sortable and filterable. Primary analyst entry point.

---

### AF-01 · Feed Header

**Components:**
- Title: "Anomaly Detection Feed"
- Sub-label: `{total count} active alerts · sorted by risk score`
- Filter button group: one button per `signal.type` plus "All" — `[CONFIGURABLE: filter labels]`
- STATE: `active filter` — button shows cyan border and tinted background

---

### AF-02 · Column Header Row

**Columns:** Provider / Signal | Anomaly Type | Risk Score | AI Confidence | At Risk | Action

**Notes:**
- Fixed, non-scrolling header row
- Column widths: `2.2fr 1fr 110px 110px 80px 100px`
- `[CONFIGURABLE: column labels]` — e.g., rename "At Risk" to "Est. Exposure" per program terminology

---

### AF-03 · Alert Row (Collapsed)

**Layout:** Grid matching AF-02 column widths.

**Left cell — Provider / Signal:**
- `provider.name` (14px, medium weight)
- `provider.npi` · `provider.city` · `provider.specialty` (monospace, muted, 10px)
- `signal.flag` chip (red background, monospace, 10px)

**Type cell:**
- `signal.type` display label (12px, dimmed)

**Risk Score cell:**
- `RiskBadge` component: colored dot + `signal.riskScore` + HIGH / MED / LOW label
- Colors: `≥90` red, `≥75` amber, `<75` green — `[CONFIGURABLE: thresholds]`

**AI Confidence cell:**
- `ConfBar` component: thin progress bar + percentage text
- Bar color: `program.color`

**At Risk cell:**
- `signal.atRisk` formatted currency (amber, bold)

**Action cell:**
- "Review" button → navigates to `/provider/{npi}`

**Interaction:** Clicking the row body (not the button) toggles the inline expansion (see AF-04).

---

### AF-04 · Alert Row (Expanded — Inline AI Reason)

**Behavior:** Appended below the collapsed row content on click. Only one row expanded at a time.

**Content:**
- Bot icon in a tinted box
- Label: `AI ANALYSIS · INLINE REASON CODE`
- Paragraph: references `signal.subtype`, `signal.confidenceLevel`, `signal.detectedAt`, and a recommended action
- Amber text callout for the recommended next step

**Domain Pack Note:** The inline reason code copy template is configurable per `signal.type`. Set the template string in the domain pack signal config.

---

## Screen: Provider Deep-Dive

**Route:** `/provider/:npi`
**Roles:** Analyst, Supervisor
**Purpose:** Full evidence dossier for a single provider. The core investigation surface.

---

### PD-01 · Provider Header Card

**Layout:** Full-width card at the top of the screen.

**Left section:**
- Provider icon: Building icon in a tinted box (color based on risk level)
- `provider.name` (21px, Oxanium bold)
- `provider.specialty` · `provider.city` · `NPI: {provider.npi}`
- Chip row: HIGH RISK | `{signal.type}` | FLAGGED `{signal.daysSinceDetection}`D AGO | `{program.label}`

**Right section:**
- Large `signal.riskScore` display (54px, Oxanium bold, red)
- "RISK SCORE / 100" label
- `ConfBar` component showing `signal.confidenceLevel` in red

---

### PD-02 · AI Signal Summary Banner

**Layout:** Full-width banner below the header card. Green-tinted border.

**Content:**
- Bot icon
- Label: `AI ANALYSIS · {N} ANOMALY SIGNALS DETECTED`
- One row per detected signal: signal icon + label (Oxanium bold) + plain-language description paragraph
- Signal colors: HCPCS Consolidation = red, E&M Upcoding = amber, Network Co-billing = purple — `[CONFIGURABLE per signal type]`

---

### PD-03 · Tab Bar

**Tabs:** Overview | Policy Analysis `PKG` | Evidence Log | Billing Timeline

- `PKG` pill badge on Policy Analysis tab in green
- Active tab: underline in `program.color`
- Inactive tabs: muted text, no underline

**Domain Pack Note:** Tabs are configurable. To add a tab (e.g., "Claim Detail" for a claims-level pack), register it in the tab config array and provide a corresponding content component.

---

### PD-TAB-A · Overview Tab

Three stacked signal evidence panels, one per detected anomaly.

#### Signal Panel Header (all panels share this pattern)
- Signal icon in a tinted box
- "Signal N · {signal name}" (Oxanium bold, 13px)
- Subtitle: plain-language description of the signal type
- Severity chip: HIGH / MEDIUM — `[CONFIGURABLE: thresholds]`

#### Signal 1 — HCPCS Code Consolidation Panel

**Left (flex: 2) — Dual-axis line chart:**
- X-axis: monthly periods (18 months)
- Left Y-axis: unique HCPCS code count (cyan line, decreasing)
- Right Y-axis: top-3 code billing concentration % (red dashed line, increasing)
- Legend below chart

**Right (flex: 1) — Stat cards + code breakdown:**
- Two stat cards: `47→6` (code diversity collapse) and `98%` (billing concentration)
- Code breakdown list: top 6 codes with `code`, `description`, `pct`, and inline progress bar
- First code (highest billing) highlighted in red

**Domain Pack Note:** The code system axis label is configurable (`HCPCS`, `CPT`, `NDC`). The consolidation threshold triggering the red highlight is configurable (default: `pct ≥ 50%` for a single code).

#### Signal 2 — E&M Level Upcoding Panel

**Left (flex: 1) — Grouped bar chart:**
- X-axis: E&M code levels (99211–99215, or equivalent for program) — `[CONFIGURABLE: code range]`
- Y-axis: % of all E&M claims
- Three bar series per code: This Provider (red), 90th Pct Peer (amber), Peer Median (cyan)

**Center (flex: 1) — Area trend chart:**
- X-axis: monthly periods
- Y-axis: utilization rate %
- Series: provider rate (red area), peer median (cyan dashed area)
- Annotation: shows divergence point

**Right (width: 160px) — Stat cards:**
- Four stat cards: provider rate, national rank, rate increase over period, estimated overbilling

**Domain Pack Note:** E&M code levels and the peer comparison metric are configurable. For non-E&M programs (e.g., DME suppliers), replace with the relevant code intensity metric.

#### Signal 3 — Network Co-billing Panel

**Left (flex: 1) — SVG Network Diagram:**
- Nodes: Subject provider (large circle) + connected flagged providers (smaller circles)
- Node size: proportional to `signal.riskScore`
- Node color: red for risk ≥90, amber for risk ≥75
- Edge width: proportional to `provider.overlap %`
- Edge label: overlap percentage displayed in a small pill
- Dashed ring around subject provider node
- Legend: Subject (red) | Flagged (amber) | edge label explanation

**Right (flex: 1) — Co-billing table + AI insight:**
- Table columns: Provider | Overlap % | Volume | Risk Score | Status
- Overlap % cell: value + inline progress bar (red if ≥30%, amber otherwise)
- AI insight callout (purple tint): combined beneficiary count + referral density ratio + interpretation

**Domain Pack Note:** The network diagram node threshold (minimum overlap % to draw an edge) is configurable. Default: draw edge if overlap ≥ 10%. The referral density multiplier baseline (4.2× expected) must be calibrated per program and specialty.

---

### PD-TAB-B · Policy Analysis Tab (PKG)

Three stacked signal-policy panels, one per anomaly signal.

#### PKG Header Banner

- GitBranch icon
- Title: "Policy Knowledge Graph — Active Analysis"
- `PKG v{version}` badge
- Summary: `{N} policy sections retrieved · Grounding complete`
- Stat: total policies indexed in the corpus

#### Per-Signal Policy Panel

**Signal panel header:**
- Signal icon, name, anomaly score, retrieved policy count
- Determination badge: LIKELY VIOLATION / POSSIBLE VIOLATION / CORNER CASE — `[CONFIGURABLE: verdict labels]`
- Confidence percentage in a stat box

**Left column (flex: 1.1) — Retrieved policy citations:**
- One citation card per retrieved policy, ordered by `citation.relevanceScore` descending
- Each card:
  - Source label with BookOpen icon (green monospace)
  - Rule type chip (e.g., "Coding Requirement")
  - Policy title
  - Relevance score ring: SVG circular progress indicator, 0–100
  - Quoted snippet with green left border (italic, truncated at 200 chars)

**Right column (flex: 0.9) — Determination + actions:**
- AI Reasoning Chain box:
  - Scale icon + "AI REASONING CHAIN" label
  - Reasoning narrative paragraph
  - Step chain visual: `Anomaly Signal → Policy Match → Peer Context → Determination`
- Compliance Actions list:
  - One card per `ComplianceAction`
  - Action type pill (IMMEDIATE / INVESTIGATION / COMPLIANCE) with priority color
  - Action label + description
- Policy Gap callout:
  - AlertCircle icon in amber
  - "POLICY GAP IDENTIFIED" label
  - Gap description

**UI States:**

| State | Trigger | Behavior |
|-------|---------|----------|
| `loading` | PKG query in flight | Skeleton placeholders in citation cards |
| `no-policy-match` | No citations above relevance threshold | Shows "No matching policy citations found" with guidance to review manually |
| `high-confidence-violation` | `determination.confidence ≥ 0.85` AND `verdict = likely_violation` | Determination badge pulses red; "Promote to Case" CTA is surfaced |

**Domain Pack Note:** The relevance threshold for surfacing citations is configurable (default: ≥70). The determination confidence threshold for auto-surfacing the "Promote to Case" CTA is configurable (default: ≥85%).

---

### PD-TAB-C · Evidence Log Tab

**Layout:** Single full-width card.

**Content:** Vertical timeline of evidence events, each with:
- Colored icon circle (red = high severity, amber = medium, cyan = info)
- Vertical connector line between events
- Event type label (bold) + date (monospace, right-aligned)
- Event description paragraph

**Event types and icons:**
| Event Type | Icon | Domain Pack Note |
|------------|------|-----------------|
| AI Detection | Bot | Always present |
| Peer Analysis | TrendingUp | Present when peer comparison run |
| Network Scan | Share2 | Present when network analysis run |
| Claims Pull | FileText | Present when claims reviewed |
| Analyst Review | User | Present when analyst adds a note |

**Domain Pack Note:** Event types are extensible. Add program-specific event types (e.g., "Site Visit Completed", "ADR Issued") by registering them in the event type config.

---

### PD-TAB-D · Billing Timeline Tab

**Layout:** Single full-width card.

**Chart type:** Area chart, single series.

**Data:** `signal.trendData` — monthly billing value in `$K` over the full detection window.

**Annotations:**
- Chart subtitle: growth percentage over the period (e.g., "442% growth over 18 months")
- Y-axis formatter: `$[value]K`

---

## Screen: Case Management

**Route:** `/cases`
**Roles:** Analyst (own cases), Supervisor (all cases)

---

### CM-01 · Case Screen Header

**Components:**
- Title: "Case Management"
- Sub-label: `{total} active cases · {escalated count} escalated · ${total_at_risk} under review`
- Filter button: opens filter panel (extend in domain pack)
- Export button: exports case list to CSV/Excel

---

### CM-02 · Case Status Summary Row

**Layout:** 5 mini stat cards in a horizontal row.

| Card | Status | Color |
|------|--------|-------|
| Pending | `pending` | Amber |
| Under Review | `under_review` | Cyan |
| Escalated | `escalated` | Red |
| Confirmed | `closed_confirmed` | Green |
| Cleared | `closed_cleared` | Muted |

Each card: large count + status label.

**Domain Pack Note:** Add or remove cards to match the program's case lifecycle statuses.

---

### CM-03 · Case Table

**Column headers:** Case ID | Provider | Type | Risk | Status | Analyst | At Risk | Opened

**Column widths:** `130px 2fr 1fr 80px 130px 120px 90px 80px`

**Per-row content:**

| Column | Content | Notes |
|--------|---------|-------|
| Case ID | `case.id` — monospace, `program.color` | Links to provider deep-dive when clicked |
| Provider | `provider.name` | 13px, medium weight |
| Type | `signal.type` display | 11px, dimmed |
| Risk | `RiskBadge` component | Shared with feed |
| Status | Status pill | Color-coded by status: see status color map below |
| Analyst | `investigator.name` | Amber if "Unassigned" |
| At Risk | `case.atRisk` | Amber if populated, muted dash if not |
| Opened | `case.openedDate` | Short format: `MMM DD` |

**Status color map:**

| Status | Color |
|--------|-------|
| `under_review` | Cyan |
| `escalated` | Red |
| `pending` | Amber |
| `closed_confirmed` | Green |
| `closed_cleared` | Muted |

**Row interaction:**
- Hover: row background tints to `s3`
- Click: expands row to show case detail (extend in domain pack — not yet implemented in reference UI)

---

## Screen: Policy Intelligence

**Route:** `/policy`
**Roles:** CMS Leader (full), Supervisor (read-only)
**Purpose:** Systemic view of policy gaps and oversight weaknesses for CMS program leadership.

---

### PI-01 · Screen Header

**Components:**
- Landmark icon + "Policy Intelligence" title
- `FOR CMS LEADERSHIP` badge (green pill, monospace)
- Subtitle: describes the screen's purpose
- "Export Policy Brief" button (right-aligned) — `[CONFIGURABLE: export format: PDF, DOCX]`

---

### PI-02 · KPI Cards Row

**Layout:** 5 cards in a horizontal flex row.

| Card | Field | Color |
|------|-------|-------|
| Policy Gaps Identified | `policyGaps.count` | Red |
| Total Estimated Exposure | `policyGaps.totalExposure` | Amber |
| Cases Exposing Gaps | `policyGaps.casesExposing` | Amber |
| Policy Change Recs | `policyGaps.recommendationCount` | Green |
| Programs Impacted | Derived from gap scope | Purple |

---

### PI-03 · Policy Gap Exposure Trend Chart

**Layout:** Left half of a two-panel row.

**Chart type:** Area chart, dual-series.

**Series:**
- Cases exploiting identified gaps (amber)
- Estimated exposure in $M (red)

**X-axis:** Quarterly periods — `[CONFIGURABLE: period granularity]`

---

### PI-04 · Gap Severity vs. Exposure Matrix

**Layout:** Right half of the same row as PI-03.

**Chart type:** Custom SVG scatter/bubble chart.

- X-axis: number of cases exposing the gap
- Y-axis: estimated exposure in $M
- Each bubble: one policy gap. Size proportional to estimated exposure. Color by severity.
- Label inside bubble: `gap.id` (short code)
- Sub-label below bubble: truncated `gap.title`

---

### PI-05 · Policy Gap Cards List

**Layout:** Full-width stacked list below the chart row.

**Section header:** `IDENTIFIED POLICY GAPS & RECOMMENDATIONS`

**Per-gap collapsed row (grid):**

| Column | Content |
|--------|---------|
| Severity dot | Colored dot — red (critical), amber (high), cyan (medium), green (low) |
| Title + Source | `gap.title` (13px) + `gap.source` (monospace, muted, 10px) |
| Severity badge | Pill chip colored by severity |
| Scope | `gap.scope` (11px, dimmed) |
| Exposure | `gap.estimatedExposure` (amber, bold) |
| Program | Program color dot + `programLabel` |
| Chevron | Rotates 90° when expanded |

**Per-gap expanded detail:**

Left column:
- "POLICY GAP DESCRIPTION" label
- `gap.description` paragraph
- Three mini stat cards: Affected Providers | Cases Exposing | Est. Total Exposure

Right column:
- "RECOMMENDED POLICY CHANGE" label
- Recommendation card with Lightbulb icon and `gap.recommendation` text
- Two action buttons: "Add to Policy Brief" | "View Affected Cases"

**UI States:**

| State | Trigger | Behavior |
|-------|---------|----------|
| `collapsed` (default) | — | Shows row summary only |
| `expanded` | Click row | Detail panel slides open below row. One card expanded at a time. |
| `deep-linked` | `?gapId=` in URL | Matching card is expanded on load |
| `filtered` | Active program in switcher | Cards with non-matching `gap.programImpact` are hidden |

**Domain Pack Note:** The severity thresholds for gap classification (`critical` / `high` / `medium` / `low`) are configurable per program's risk appetite. The policy brief export format (PDF vs. DOCX) is configurable in the domain pack.

---

## Component Library Summary

Reusable components shared across screens. Configure defaults in the domain pack theme file.

| Component | Used In | Key Props | Domain Pack Config |
|-----------|---------|-----------|-------------------|
| `RiskBadge` | Feed, Provider Header, Case Table | `score` | Threshold bands (90/75 defaults) |
| `ConfBar` | Feed, Provider Header | `val`, `color` | Bar color defaults to `program.color` |
| `Chip` | Feed, Provider Header, Feed Inline | `label`, `color` | Labels configurable per signal type |
| `KPICard` | Dashboard, Policy Intelligence | `icon`, `label`, `value`, `sub`, `color`, `trend` | All props configurable |
| `SignalPanelHeader` | Provider Deep-Dive Overview | `signalNum`, `title`, `subtitle`, `severity`, `color` | Severity label and color configurable |
| `PolicyCitationCard` | Provider Deep-Dive Policy tab | `citation` | Relevance ring color fixed to green |
| `RelevanceRing` | Provider Deep-Dive Policy tab | `value` | SVG component, 36px diameter |
| `StepChain` | Provider Deep-Dive Policy tab | `steps[]` | Step labels configurable per signal type |
| `ComplianceActionCard` | Provider Deep-Dive Policy tab | `action` | Action type labels configurable |
| `NetworkDiagram` | Provider Deep-Dive Overview | `nodes[]`, `edges[]` | Edge threshold configurable |
| `GapCard` | Policy Intelligence | `gap` | Severity thresholds configurable |

---

## Domain Pack — Screen-Level Configuration Checklist

For each new program pack, review these screen-level configuration points:

- [ ] **Dashboard:** Set KPI card labels and period label per program (`kpi.period`)
- [ ] **Dashboard — Queue Health:** Set `maxCases` denominator for capacity calculation
- [ ] **Anomaly Feed:** Configure filter button labels per `signal.type` enum for the program
- [ ] **Anomaly Feed — Inline Reason Code:** Set per-signal copy template strings
- [ ] **Provider Deep-Dive — Overview:** Configure code system label (HCPCS / CPT / NDC); set peer comparison metric per signal type; calibrate network edge threshold and referral density baseline
- [ ] **Provider Deep-Dive — Policy tab:** Set PKG retrieval relevance threshold; set determination confidence threshold for "Promote to Case" CTA; configure verdict label strings
- [ ] **Provider Deep-Dive — Evidence Log:** Register program-specific event types
- [ ] **Case Management:** Configure case ID prefix; extend status enum and status color map
- [ ] **Policy Intelligence:** Set severity thresholds; configure export format; set chart period granularity
- [ ] **All screens:** Confirm role access matrix matches program's organizational structure (see `navigation_flow.md`)
