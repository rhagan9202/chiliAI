# Component Library
**IntegrityAI · Program Integrity Accelerator**
`domain-pack/docs/component_library.md`

---

## Overview

This document specifies every reusable component in the IntegrityAI UI. Each entry covers:
- **Visual anatomy** — what the component looks like and its exact style values
- **Props** — the data it accepts
- **States** — all visual variants
- **Usage rules** — where it appears, where it must not appear
- **Domain pack notes** — what is configurable

All style values reference design tokens from `design_system.md`. Token names (`C.red`, `C.cyan`, etc.) are used directly rather than repeating hex values.

---

## CMP-01 · RiskBadge

**Purpose:** Displays a provider or signal's composite AI risk score with a color-coded severity indicator.

**Appears in:** Anomaly Feed rows, Provider Deep-Dive header, Case Management table

### Visual Anatomy

```
[● 94 HIGH]

● = colored dot, 7×7px, border-radius 50%
    box-shadow: 0 0 6px {color}   ← glow effect
94 = Oxanium, 14px, weight 700, color = {color}
HIGH = Oxanium, 10px, weight 500, color = C.muted
    displayed inline after the score with a space

Layout: flex row, align-items center, gap 6px
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `score` | `integer 0–100` | The risk score value to display |

### States

| State | Score Range | Color |
|-------|-------------|-------|
| HIGH | ≥ 90 | `C.red` |
| MED | 75–89 | `C.amber` |
| LOW | < 75 | `C.green` |

> **Domain pack note:** Threshold values (90, 75) are hardcoded in the component. To adjust thresholds for a new program, update the conditional logic in the component definition.

---

## CMP-02 · ConfBar

**Purpose:** Displays an AI model confidence level as a thin labeled progress bar.

**Appears in:** Anomaly Feed rows, Provider Deep-Dive header

### Visual Anatomy

```
[████████░░░░] 89%

Container: flex row, align-items center, gap 8px, width 100%
Bar track:  flex:1, height 3px, background C.b0, border-radius 2px, overflow hidden
Bar fill:   width {val}%, height 100%, background {color}, border-radius 2px
Label:      IBM Plex Mono, 10px, color C.dim, min-width 28px
```

### Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `val` | `integer 0–100` | required | Confidence percentage |
| `color` | `hex string` | `C.cyan` | Fill color of the progress bar |

### Usage Rules
- In the Feed: uses default `C.cyan`
- In the Provider header (when risk is high): pass `C.red` as color
- Never use amber or green for this component — they imply a different semantic meaning

---

## CMP-03 · Chip

**Purpose:** Compact label pill for categorical flags, signal types, status, and badges.

**Appears in:** Feed rows (signal flags), Provider Deep-Dive header (signal type, risk level, program), Policy tab (rule type, determination), Policy Intelligence (severity, program)

### Visual Anatomy

```
[HIGH RISK]

padding: 2px 8px
border-radius: 4px
border: 1px solid ${color}30
background: ${color}10
font: IBM Plex Mono, 9–10px
color: {semantic color}
letter-spacing: 0.04–0.07em
white-space: nowrap
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `label` | `string` | Text displayed in the chip |
| `color` | `hex string` | Semantic color — sets text, border, and background tint |

### Common Color Assignments

| Label | Color |
|-------|-------|
| HIGH RISK | `C.red` |
| HIGH SEVERITY / CRITICAL | `C.red` |
| MEDIUM SEVERITY | `C.purple` |
| LIKELY VIOLATION | `C.red` |
| POSSIBLE VIOLATION | `C.amber` |
| PKG (badge) | `C.green` |
| FLAGGED Xd AGO | `C.cyan` |
| Program label (Medicare) | `C.cyan` |
| Program label (Medicaid) | `C.purple` |
| Rule type (generic) | `C.muted` (uses `C.b1` as background) |

---

## CMP-04 · KPICard

**Purpose:** Summary metric card displayed in a horizontal row on the Dashboard and Policy Intelligence screens.

**Appears in:** Dashboard (4 cards), Policy Intelligence (5 cards)

### Visual Anatomy

```
┌─────────────────────────────┐
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │  ← 2px top accent line (gradient)
│                             │
│  [icon box]    +12% QoQ ↑  │
│                             │
│  $52.7M                     │
│  Potential Recovery         │
│  Est. recoverable overpay…  │
└─────────────────────────────┘

Outer card:
  flex: 1
  background: C.s2
  border: 1px solid C.b0
  border-radius: 12px
  padding: 20px 22px
  position: relative, overflow: hidden

Top accent line (absolute):
  top: 0, left: 0, right: 0, height: 2px
  background: linear-gradient(90deg, transparent, ${color}80, transparent)

Icon box:
  padding: 8px, border-radius: 8px
  background: ${color}15
  width/height: auto (fits icon)

Trend indicator (optional, right-aligned):
  font: IBM Plex Mono, 11px
  color: C.green
  display: flex, align-items: center, gap: 3px
  ArrowUp icon: 10px

Value:
  Oxanium, 26px, weight 800, color C.text, line-height 1

Label:
  IBM Plex Sans, 12px, color C.dim, margin-top 5px

Sub-label:
  IBM Plex Sans, 11px, color C.muted, margin-top 3px
```

### Props

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `icon` | Lucide component | ✅ | Icon to display in the icon box |
| `label` | `string` | ✅ | Primary metric label |
| `value` | `string` | ✅ | The displayed value (pre-formatted) |
| `sub` | `string` | ❌ | Sub-label below the metric label |
| `color` | `hex string` | ✅ | Semantic color — drives icon box, accent line |
| `trend` | `string` | ❌ | If provided, renders trend indicator (e.g., `"+12% QoQ"`) |

---

## CMP-05 · SignalPanelHeader

**Purpose:** Standard colored header strip for each anomaly signal evidence panel in the Provider Deep-Dive Overview tab.

**Appears in:** Provider Deep-Dive — Overview tab (once per signal)

### Visual Anatomy

```
┌──────────────────────────────────────────────────────────────┐
│ [icon box]  Signal 1 · HCPCS Code Consolidation              [HIGH SEVERITY chip]
│             Systematic reduction in procedure code diversity… │
└──────────────────────────────────────────────────────────────┘

Container:
  padding: 14px 20px
  background: ${signal.color}08
  border-bottom: 1px solid C.b0
  display: flex, justify-content: space-between, align-items: center

Icon box:
  width: 24px, height: 24px, border-radius: 6px
  background: ${signal.color}20
  contains: signal icon at 13px

Title:
  Oxanium, 13px, weight 700, color C.text

Subtitle:
  IBM Plex Sans, 11px, color C.dim, margin-top: 1px

Right: Chip component with severity label and signal color
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `signalNum` | `integer` | Display number (1, 2, 3) |
| `title` | `string` | Signal name |
| `subtitle` | `string` | Plain-language description |
| `severity` | `string` | Severity label for the chip (e.g., "HIGH SEVERITY") |
| `icon` | Lucide component | Signal-specific icon |
| `color` | `hex string` | Signal semantic color |

---

## CMP-06 · PolicyCitationCard

**Purpose:** Displays a single retrieved policy document section from the PKG, with relevance score, source citation, rule type, title, and text snippet.

**Appears in:** Provider Deep-Dive — Policy Analysis tab (multiple per signal)

### Visual Anatomy

```
┌────────────────────────────────────────────────────────┐
│  📖 CMS IOM Pub. 100-04, Ch. 12 §30.6.1  [Coding Req] │  ← 97
│  E&M Documentation Requirements — Level of Service…   │  [ring]
│                                                        │
│  ▎ "The selection of the appropriate level of E&M      │
│    service must be based on the key components…"       │
└────────────────────────────────────────────────────────┘

Container:
  background: C.s3
  border: 1px solid C.b0
  border-radius: 9px
  padding: 12px 14px

Header row: space-between
  Left:
    Source line: BookOpen icon (11px, C.green) + source string
      (IBM Plex Mono, 9px, C.green) + rule type chip
    Title: IBM Plex Sans, 12px, weight 500, C.text, line-height 1.4

  Right: RelevanceRing component (see CMP-07)

Snippet:
  IBM Plex Sans, 11px, color C.dim, line-height 1.65
  font-style: italic
  border-left: 2px solid ${C.green}40
  padding-left: 10px
  Max display: 200 chars, truncate with "…"
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `citation` | `PolicyCitation` | Full citation object from fields_dictionary.md |

---

## CMP-07 · RelevanceRing

**Purpose:** Circular SVG progress indicator showing a PKG citation's relevance score as a percentage arc.

**Appears in:** PolicyCitationCard (top-right of each card)

### Visual Anatomy

```
     ╭──╮
    │ 97 │   ← IBM Plex Mono, 9px, C.green, weight 600
     ╰──╯
  REL%       ← IBM Plex Mono, 7px, C.muted

SVG: viewBox 36×36, width 36px, height 36px

Outer track circle:
  cx 18, cy 18, r 14
  fill: none, stroke: C.b0, stroke-width: 3

Fill arc:
  cx 18, cy 18, r 14
  fill: none, stroke: C.green, stroke-width: 3
  stroke-dasharray: {score * 0.879} 87.9
    (87.9 = 2πr = 2 × 3.14159 × 14)
  stroke-linecap: round
  transform: rotate(-90deg)  applied to SVG element to start arc at top

Center text: absolute positioned over SVG
  inset: 0, display: flex, align-items: center, justify-content: center
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `value` | `integer 0–100` | Relevance score to display |

### Calculation Note
`stroke-dasharray` first value = `value × 0.879`
The full circumference of a circle with r=14 is `2π×14 ≈ 87.96`, so each percentage point = `0.8796` units of dasharray. Approximated to `0.879` for conciseness.

---

## CMP-08 · ComplianceActionCard

**Purpose:** Displays a single recommended compliance or investigative action derived from PKG policy analysis.

**Appears in:** Provider Deep-Dive — Policy Analysis tab (multiple per signal)

### Visual Anatomy

```
┌──────────────────────────────────────────────────────────────┐
│  [IMMEDIATE]  Prepayment Edit                                │
│               Place provider on prepayment review for        │
│               codes 99215 and 64483 pending investigation.   │
└──────────────────────────────────────────────────────────────┘

Container:
  background: C.s3
  border: 1px solid C.b0
  border-radius: 8px
  padding: 10px 12px
  display: flex, gap: 10px, align-items: flex-start

Type pill:
  padding: 3px 7px, border-radius: 4px
  background: ${priorityColor}15
  border: 1px solid ${priorityColor}30
  IBM Plex Mono, 8px, color: {priorityColor}
  white-space: nowrap, margin-top: 1px

Priority → color mapping:
  high   → C.red
  medium → C.amber
  low    → C.cyan

Label:
  IBM Plex Sans, 12px, weight 600, C.text, margin-bottom: 3px

Description:
  IBM Plex Sans, 11px, C.dim, line-height: 1.5
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `action` | `ComplianceAction` | Action object from fields_dictionary.md |

---

## CMP-09 · StepChain

**Purpose:** Visual reasoning chain showing the AI's analytical steps from signal to determination.

**Appears in:** Provider Deep-Dive — Policy Analysis tab (once per signal, inside the reasoning box)

### Visual Anatomy

```
[Anomaly Signal] → [Policy Match] → [Peer Context] → [Determination]

Each step pill:
  padding: 3px 8px, border-radius: 4px
  background: ${detColor}15
  border: 1px solid ${detColor}30
  IBM Plex Mono, 9px, color: {detColor}

Separator (ArrowRight icon):
  size: 9px, color: C.muted

Container:
  display: flex, align-items: center, gap: 6px
  flex-wrap: wrap
  margin-top: 11px
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `steps` | `string[]` | Array of step label strings |
| `color` | `hex string` | Determination color (red / amber / green) |

### Default Steps
`["Anomaly Signal", "Policy Match", "Peer Context", "Determination"]`

> **Domain pack note:** Steps can be relabeled but the 4-step structure should be preserved for visual consistency.

---

## CMP-10 · PolicyGapCallout

**Purpose:** Amber-tinted callout box surfacing an identified CMS policy gap or ambiguity.

**Appears in:** Provider Deep-Dive — Policy Analysis tab (once per signal)

### Visual Anatomy

```
┌─────────────────────────────────────────────────────────────┐
│ ⚠  POLICY GAP IDENTIFIED                                    │
│    IOM §30.6.1 lacks a quantitative threshold for code      │
│    concentration ratios, creating enforcement ambiguity…    │
└─────────────────────────────────────────────────────────────┘

Container:
  padding: 10px 13px
  background: ${C.amber}07
  border: 1px solid ${C.amber}20
  border-radius: 8px
  display: flex, gap: 8px, align-items: flex-start

Icon: AlertCircle, 13px, C.amber, flex-shrink: 0, margin-top: 2px

Header:
  IBM Plex Mono, 8px, C.amber, letter-spacing: 0.07em, margin-bottom: 4px
  Text: "POLICY GAP IDENTIFIED"

Body:
  IBM Plex Sans, 11px, C.dim, line-height: 1.6
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `text` | `string` | The gap description paragraph |

---

## CMP-11 · NetworkDiagram

**Purpose:** Custom SVG node-edge diagram showing provider co-billing relationships with overlap percentages.

**Appears in:** Provider Deep-Dive — Overview tab, Signal 3 (Network Co-billing)

### Visual Anatomy

```
SVG viewBox: "0 0 435 275", width: 100%

Background grid:
  Vertical lines every 50px: stroke C.b0, stroke-width 0.5, opacity 0.5
  Horizontal lines every 50px: same

Edges:
  <line> from node center to node center
  stroke: C.purple (subject edges) or C.muted (peer-to-peer edges)
  stroke-width: proportional to overlap % (scale: overlap/10, min 1.2, max 3.8)
  opacity: 0.45
  strokeDasharray: used for non-subject edges only

Edge labels (overlap %):
  <rect> 28×15px, rx 3, fill C.s1, stroke C.b1, stroke-width 0.8
  <text> IBM Plex Mono, 8px, C.dim, centered in rect

Nodes:
  Outer dashed ring (subject node only):
    r = nodeR + 8, stroke: node.color, stroke-width 1, opacity 0.25, strokeDasharray "4 3"
  Main circle:
    fill: ${node.color}18, stroke: node.color
    stroke-width: 2 (subject), 1.5 (others)
    r: proportional to risk score (subject: 40, others: 18–24)
  Name text: IBM Plex Sans, 7–8px, C.text, centered, 2 lines split by \n
  Risk badge rect: 26×12px, rx 3, positioned at top-right of node
    fill: ${color}22, stroke: ${color}60, stroke-width 0.8
  Risk badge text: IBM Plex Mono, 7.5px, node.color, weight 600
  Status dot: circle r 3.5
    fill: C.red (subject), C.amber (flagged peers)
    positioned at top-left of node circle

Legend (bottom of SVG):
  Subject sample circle + label
  Flagged sample circle + label
  Text: "── edge label = shared patient %"
  IBM Plex Sans, 8px, C.dim
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `nodes` | `NetworkNode[]` | Provider nodes with `id, label, x, y, r, color, risk, status` |
| `edges` | `NetworkEdge[]` | Connections with `from, to, overlap, vol, w` (w = stroke width) |

### NetworkNode Schema
```
{ id: string, label: string (use \n for line break),
  x: number, y: number, r: number,
  color: hex string, risk: integer, status: 'SUBJECT' | 'FLAGGED' }
```

### NetworkEdge Schema
```
{ from: string (node id), to: string (node id),
  overlap: integer (%), vol: integer (patient count), w: number (stroke-width) }
```

> **Domain pack note:** Node positions (`x`, `y`) are manually set for the demo. In production, apply a force-directed layout algorithm (e.g., D3-force) to compute positions automatically from the graph data.

---

## CMP-12 · PolicyGapCard

**Purpose:** Collapsible card displaying a single identified CMS policy gap with description, stats, and policy change recommendation. Used in the Policy Intelligence screen.

**Appears in:** Policy Intelligence screen

### Visual Anatomy — Collapsed

```
● Title of Gap                    [SEVERITY]  Scope  $Exposure  ● Program  >

Outer card:
  background: C.s2, border: 1px solid C.b0 (default) or C.b2 (expanded)
  border-radius: 11px, overflow: hidden

Row grid: 26px 1fr 130px 110px 100px 130px 42px
  padding: 13px 18px, cursor: pointer, align-items: center, gap: 8px

Severity dot: 8×8px circle, box-shadow: 0 0 6px {color}
  C.red (CRITICAL), C.amber (HIGH), C.cyan (MEDIUM), C.green (LOW)

Title: IBM Plex Sans, 13px, weight 500, C.text
Source: IBM Plex Mono, 10px, C.muted (below title)

Severity chip: Chip component with severity color
Scope: IBM Plex Sans, 11px, C.dim
Exposure: Oxanium, 13px, weight 700, C.amber
Program dot + label: 7px colored circle + IBM Plex Sans, 11px, C.dim
Chevron: ChevronRight icon, 14px, C.muted
  transform: rotate(90deg) when expanded, transition: 0.2s
```

### Visual Anatomy — Expanded (appended below collapsed row)

```
┌─ left column ──────────────────┬─ right column ──────────────────┐
│ POLICY GAP DESCRIPTION          │ RECOMMENDED POLICY CHANGE        │
│ {gap.description}               │ [💡 gap.recommendation]          │
│                                 │                                  │
│ [stat] [stat] [stat]            │ [Add to Policy Brief] [View…]    │
└─────────────────────────────────┴──────────────────────────────────┘

Expanded container:
  border-top: 1px solid C.b0
  padding: 16px 20px
  background: C.s3
  display: flex, gap: 18px
  animation: fadeUp 0.35s ease

Left column:
  Section label: IBM Plex Mono, 9px, C.muted, letter-spacing 0.07em
  Description: IBM Plex Sans, 12px, C.dim, line-height 1.7
  3 stat mini-cards: background C.s2, border C.b0, border-radius 8px, padding 10px 12px
    Value: Oxanium 18px weight 800 (amber or red)
    Label: IBM Plex Sans 10px C.muted

Right column:
  Section label: IBM Plex Mono, 9px, C.green, letter-spacing 0.07em
  Recommendation box:
    padding: 13px 15px, background: ${C.green}07
    border: 1px solid ${C.green}20, border-radius: 9px
    Lightbulb icon 13px C.green + text IBM Plex Sans 12px C.dim line-height 1.7
  Two action buttons:
    "Add to Policy Brief": border ${C.green}40, background ${C.green}10, color C.green
    "View Affected Cases": border C.b1, background transparent, color C.dim
    Both: padding 8px 0, border-radius 7px, Oxanium weight 600 11px
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `gap` | `PolicyGap` | Full gap object from fields_dictionary.md |
| `isOpen` | `boolean` | Whether the expanded detail is visible |
| `onToggle` | `function` | Called when row is clicked |

---

## CMP-13 · AIInsightCallout

**Purpose:** Tinted box with Bot icon delivering a contextual AI-generated insight or summary within a data panel.

**Appears in:** Provider Deep-Dive — Overview tab Signal 3, inline expanded rows in Feed

### Visual Anatomy

```
┌──────────────────────────────────────────────────────────────┐
│ 🤖  All 4 connected providers are independently flagged.     │
│     Combined shared-patient volume of 636 beneficiaries.     │
│     Referral density is 4.2× expected…                       │
└──────────────────────────────────────────────────────────────┘

Container:
  padding: 11px 14px (standard) or 16px (full-width)
  background: ${color}08 (typically C.cyan or C.purple)
  border: 1px solid ${color}22
  border-radius: 8px
  display: flex, gap: 8–9px, align-items: flex-start

Bot icon: 13–14px, {color}, flex-shrink: 0, margin-top: 2px

Content:
  Label (optional): IBM Plex Mono, 10px, {color}, letter-spacing 0.06em, margin-bottom 7px
  Body: IBM Plex Sans, 11–13px, C.dim, line-height 1.65–1.75
  Highlighted terms: color C.text, font-weight 500
  Secondary highlights: color {accent color}
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `label` | `string` | Optional header label (e.g., "AI ANALYSIS · INLINE REASON CODE") |
| `text` | `string` or `ReactNode` | Body content |
| `color` | `hex string` | Accent color for border, icon, label. Default: `C.cyan` |

---

## CMP-14 · PKGBanner

**Purpose:** Full-width banner summarizing the Policy Knowledge Graph analysis status for a provider. Establishes context at the top of the Policy Analysis tab.

**Appears in:** Provider Deep-Dive — Policy Analysis tab (once, at the top)

### Visual Anatomy

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [GitBranch icon]  Policy Knowledge Graph — Active Analysis  [PKG v2.4]   │
│                   3 anomaly signals queried against CMS policy corpus ·  │
│                   8 policy sections retrieved · Grounding complete.       │
│                                                         POLICIES INDEXED  │
│                                                               14,382      │
│                                                         CMS docs·CFR·SSA │
└──────────────────────────────────────────────────────────────────────────┘

Container:
  padding: 14px 20px
  background: ${C.green}07
  border: 1px solid ${C.green}20
  border-radius: 12px
  display: flex, gap: 14px, align-items: center

Icon box:
  padding: 10px, border-radius: 10px, background: ${C.green}15
  GitBranch icon: 20px, C.green

Title row:
  "Policy Knowledge Graph — Active Analysis": Oxanium, 14px, weight 700, C.text
  Version badge: Chip with "PKG v{version}" in C.green

Subtitle: IBM Plex Sans, 12px, C.dim, line-height 1.6
  Highlights: C.text for retrieved count

Right stat block (text-align right, flex-shrink: 0):
  Label: IBM Plex Mono, 9px, C.muted
  Count: Oxanium, 22px, weight 800, C.green
  Sub-label: IBM Plex Mono, 9px, C.muted
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `signalCount` | `integer` | Number of anomaly signals analyzed |
| `policyCount` | `integer` | Number of policy sections retrieved |
| `corpusSize` | `string` | Total policies indexed (e.g., "14,382") |
| `corpusSources` | `string` | Short corpus description (e.g., "CMS docs · CFR · SSA · OIG") |
| `version` | `string` | PKG version string (e.g., "2.4") |

---

## CMP-15 · ProgramSwitcher

**Purpose:** Toggle button group that switches the active program context, reaccenting the entire UI.

**Appears in:** Sidebar (always visible)

### Visual Anatomy

```
PROGRAM

[MEDICARE] [MEDICAID]

Label:
  IBM Plex Mono, 9px, C.muted, letter-spacing 0.08em

Toggle container:
  display: flex, background: C.s2, border-radius: 8px
  padding: 3px, border: 1px solid C.b0

Each button:
  flex: 1, padding: 7px 0, border-radius: 5px, border: none
  Oxanium, 9px, weight 800, letter-spacing 0.05em
  cursor: pointer, transition: all 0.2s

Active state:
  background: {program.color}
  color: '#000'  ← black text on colored background

Inactive state:
  background: transparent
  color: C.muted
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `programs` | `Program[]` | Array of program config objects |
| `active` | `string` | Active program ID |
| `onChange` | `function` | Called with new program ID on toggle |

---

## CMP-16 · InvestigatorQueueCard

**Purpose:** Mini card showing a single investigator's workload statistics and capacity utilization bar.

**Appears in:** Dashboard — Investigator Queue Health section

### Visual Anatomy

```
┌──────────────────────────┐
│  J. Morrison             │
│                          │
│  [8]    [3]    [24]      │
│ Active Pending Closed    │
│                          │
│  Capacity 73%            │
│  ████████████░░░░        │
└──────────────────────────┘

Container:
  flex: 1, background: C.s3
  border: 1px solid C.b0, border-radius: 10px, padding: 14px

Name: IBM Plex Sans, 12px, weight 600, C.text, margin-bottom: 10px

Stat blocks: flex row, gap: 10px
  Each block: flex: 1, text-align: center
    Value: Oxanium, 20px, weight 700
      Active → C.cyan, Pending → C.amber, Closed → C.green
    Label: IBM Plex Sans, 9px, C.muted, margin-top: 1px

Capacity label: IBM Plex Sans, 10px, C.muted, margin-bottom: 5px

Capacity bar:
  height: 4px, background: C.b0, border-radius: 2px, overflow: hidden
  Fill: width {pct}%, border-radius: 2px
    ≥ 80% → C.red
    ≥ 60% → C.amber
    < 60%  → C.green

Unassigned variant: no capacity bar shown; pending count displayed in amber
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `name` | `string` | Investigator display name |
| `active` | `integer` | Active case count |
| `pending` | `integer` | Pending case count |
| `closed` | `integer` | Closed case count (this quarter) |
| `load` | `integer 0–100` | Capacity utilization percentage. Pass `0` for Unassigned slot. |

---

## CMP-17 · AIPanelMessage

**Purpose:** Individual message bubble in the AI Investigator panel conversation thread.

**Appears in:** AI Investigator Panel — message thread

### Visual Anatomy — Assistant Message

```
[🤖]  ┌─────────────────────────────────────────┐
      │ I've analyzed Advanced Pain Specialists… │
      └─────────────────────────────────────────┘

Bot avatar:
  28×28px, border-radius: 7px
  background: ${C.cyan}15
  Bot icon: 14px, C.cyan
  flex-shrink: 0, margin-top: 2px

Bubble:
  background: C.s2, border: 1px solid C.b0, border-radius: 10px
  padding: 11px 13px, max-width: 88%
  font: IBM Plex Sans, 12px, C.text, line-height: 1.75
  white-space: pre-wrap  ← preserves newlines and bullet formatting
```

### Visual Anatomy — User Message (right-aligned)

```
                        ┌────────────────────────────────┐
                        │ What codes are involved?       │
                        └────────────────────────────────┘

Bubble:
  background: ${C.cyan}12, border: 1px solid ${C.cyan}28
  (same other styles as assistant, but right-aligned, no avatar)
```

### Props

| Prop | Type | Description |
|------|------|-------------|
| `role` | `'user' \| 'assistant'` | Determines alignment, background, and avatar presence |
| `text` | `string` | Message content (pre-wrap formatted) |

---

## Component Dependency Map

Quick reference: which components compose into which parent components.

```
Screen: Dashboard
├── KPICard (×4)                          CMP-04
├── AreaChart (Recharts, custom styled)
├── BarChart (Recharts, custom styled)
└── InvestigatorQueueCard (×N)            CMP-16

Screen: Anomaly Feed
├── [feed row collapsed]
│   ├── RiskBadge                         CMP-01
│   ├── ConfBar                           CMP-02
│   └── Chip (signal flag)               CMP-03
└── [feed row expanded]
    └── AIInsightCallout                  CMP-13

Screen: Provider Deep-Dive
├── [header card]
│   ├── Chip (×4)                        CMP-03
│   └── ConfBar                          CMP-02
├── [AI signal summary]
│   └── AIInsightCallout (×3 signals)   CMP-13
├── Tab: Overview
│   ├── SignalPanelHeader (×3)           CMP-05
│   ├── NetworkDiagram (Signal 3)        CMP-11
│   └── Recharts charts (Signals 1,2)
├── Tab: Policy Analysis
│   ├── PKGBanner                        CMP-14
│   └── [per signal panel]
│       ├── PolicyCitationCard (×N)      CMP-06
│       │   └── RelevanceRing            CMP-07
│       ├── StepChain                    CMP-09
│       ├── ComplianceActionCard (×N)    CMP-08
│       └── PolicyGapCallout             CMP-10
├── Tab: Evidence Log
│   └── [timeline items — inline]
└── Tab: Billing Timeline
    └── AreaChart (Recharts, custom styled)

Screen: Case Management
├── [status summary cards — inline]
└── [case table rows]
    └── RiskBadge                        CMP-01

Screen: Policy Intelligence
├── KPICard (×5)                         CMP-04
├── AreaChart (Recharts, trend)
├── SVG bubble chart (custom)
└── PolicyGapCard (×N)                   CMP-12

Overlay: AI Investigator Panel
├── [suggested prompt chips — inline]
└── AIPanelMessage (×N)                  CMP-17
```
