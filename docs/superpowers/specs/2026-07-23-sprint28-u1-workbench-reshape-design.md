# Sprint 2026-28 U1 — Workbench Reshape Design Pass (IntegrityAI-Inspired)

**Date:** 2026-07-23
**Story:** BL-049 (U1) — workbench reshape design pass, design-only.
**Status:** design for approval; U2 (BL-050, 8 SP) executes it.
**Parent design note:** `docs/superpowers/specs/2026-07-16-sprint28-cms-fraud-workbench-design.md` (§3.2)
**Reference material:** `ui_reference_code/code-starters/ui/integrity-ai.jsx` (mockup),
`ui_reference_code/demo/presenter-script.md` (what the demo narrative needs the UI to carry).
No application code changes in this story.

## 1. Current state (code-verified 2026-07-23 on `feat/sprint-2026-28-b2-timeseries-anomalies`)

### 1.1 The token system already *is* the IntegrityAI system — the pages don't use it with conviction

`chili_app/src/theme/global.css` already defines the exact mockup palette and
type stack: `--c-bg #05080f`, surfaces `--c-s1/s2/s3`, borders `--c-b0/b1/b2`,
accents `--c-cyan #00d4ff` / `--c-amber` / `--c-red` / `--c-green` /
`--c-purple #a855f7`, text `--c-text/dim/muted`, and `--font-display`
(Oxanium) / `--font-body` (IBM Plex Sans) / `--font-mono` (IBM Plex Mono).
`pages.css` (1111 lines) and `ui.css` reference the vars ~107 times and use
`--font-display` in ~8 places. What the mockup has and the app lacks is not
tokens but **ritualized usage**: mono uppercase eyebrows, oversized Oxanium
numerals for risk, tinted callout bands (`color` at 6–15% alpha background +
18–30% alpha border), uppercase underlined tab strips, and flag labels that
name the anomaly. The reshape is a hierarchy-and-usage pass, not a re-theme.

### 1.2 Investigation Workbench

`src/pages/InvestigationWorkbenchPage.tsx` (445 lines) composes everything
inline from the `ui/` kit: KB select + search card → two-column
`investigation-layout` (entity summary card, risk-factors card) →
`dashboard-panels` (timeseries `ChartFrameInvestigation`, graph neighborhood
card with depth select + `GraphCanvas`) → `EvidencePackViewer` when the
selected entity has an alert. All labels flow through `useDomainConfig()` +
`src/utils/domainDisplay.ts` (`getEntityTitle/Subtitle/Chips/TypeLabel`).
Availability handling uses the `availability_status`/`unavailable_reason`
pattern (lines 365–385).

Three **orphan components** exist in `src/components/investigation/` — mounted
by no route, exercised only by their own unit tests:

- `EntityDetailPanel.tsx` (+ CSS module) — already renders a "Community" row
  via `communityIdFor` and an a11y-correct risk meter, but hardcodes English
  labels, shows raw `entity.type` and raw property keys (bypasses
  `domainDisplay.ts` entirely — violates this story's hard constraint).
- `EvidencePanel.tsx` (+ CSS module) — functional duplicate of the live
  `EvidencePackViewer`, older `EvidencePack` shape.
- `TimelinePanel.tsx` — inline styles with light-theme fallback values
  (`var(--bg, #fff)`, `var(--accent, #aa3bff)`) that are off-palette; derives
  "events" from `created_at/updated_at` only (no real event source exists).

`src/utils/graphStyles.ts` exports `communityIdFor` (line 56), consumed only
by the orphan `EntityDetailPanel`.

### 1.3 GraphCanvas

`src/components/investigation/GraphCanvas.tsx` (react-force-graph-2d): node
color by entity type (`colorForEntityType`), node size by
`riskScoreFor` (reads `risk_score` from properties/metadata — B1's write-back
already feeds this), selected node `#fbbf24`, **uniform link color**
`rgba(120,170,255,0.35)` (line 262), no dashed/predicted treatment, no
community coloring. The underlying `force-graph` dependency supports
`linkLineDash` (verified in `node_modules/force-graph/dist/force-graph.d.ts:94`),
so dashed predicted links need no library change.

### 1.4 Dashboard and Alert Feed

- `DashboardPage.tsx`: 3 tabs (Overview / Queue Health / Policy Signals);
  KPI band of four `KpiCard`s; Policy Signals already wires `useGnnClusters`
  into a Graph clusters panel (lines 303–320, empty until B1 data),
  Top-risk entities, and a Metric Trend `ChartFrame`. Header still says
  "Phase 5 data live" (stale copy).
- `AlertFeedPage.tsx`: filterable card rows with severity/status/tag chips,
  Investigate / Ask AI / View evidence / Promote / Ack actions. The expanded
  `EvidencePackViewer` is passed `subgraph={{ nodes: [], edges: [] }}` and
  `entityTypes={[]}` (line 201) — the pack's subgraph section always renders
  the "No subgraph" empty state on this page.
- `EvidencePackViewer.tsx`: `pack.reasoning` is rendered as an ordinary
  paragraph under a "Evidence pack" strong tag; no attribution section.
  `EvidencePackResponse` has no attribution field (verified in
  `src/lib/api/schema.ts`): `reasoning`, `confidence`, `scores`, `items`,
  `policy_citations`, `subgraph_node_ids/edge_ids` only.
- Policy items surface **only** on `PolicyIntelligencePage`; `usePolicyItems`
  exists (`src/api/policy.ts:37`) and `PolicyItemSummaryResponse` carries
  `target_kind: "entity" | "alert" | "metric"` + `target_ref`, so
  entity/alert-scoped policy panels are pure client-side filtering — **no
  contract change needed**.

### 1.5 Domain-config surface (the hard constraint's machinery)

- Nav, routes, and page gating are config-driven: `Sidebar.tsx` maps
  `domainConfig.ui.navigation.pages` (id/label/route/capability) with
  role-based `enabled_pages` from `useDomainFeatures()`; `AppShell.tsx`
  redirects blocked routes. The AI assistant panel already exists app-wide
  (`uiStore.aiPanelOpen`, `AiAssistantPanel` in `AppShell.tsx:91`) — the
  mockup's right-side AI panel is **already built**; no new panel needed.
- Capabilities (`config/schema.py` → `DomainCapabilities`): `timeseries`,
  `gnn`, `risk_scoring`, `rag_chat`, `explainability`,
  `structured_ingestion`, `peer_stats`.
- CMS pack (`medicare_fraud_cms_desynpuf.yaml`): all capabilities true; nav
  includes dashboard/alerts/investigation (investigation gated on `gnn`).
- **Housing pack** (`department_air_force_housing.yaml`): `gnn: false`,
  `peer_stats: false`, `timeseries/risk_scoring/rag_chat/explainability:
  true`; its nav contains only housing / knowledge_bases / rag_chat /
  configuration — dashboard, alerts, and investigation are not routed at all.
  "Housing must render correctly" therefore means: (a) nothing in the reshape
  may assume CMS strings or entity types, and (b) every new surface must
  behave when its capability is false, because packs like housing can enable
  the workbench pages later without enabling `gnn`/`peer_stats`.

### 1.6 What the IntegrityAI mockup + presenter script actually sell

Mined from `integrity-ai.jsx` (2,760 lines) and `presenter-script.md`. The
persuasive elements, in the order the demo script leans on them:

1. **Risk-ranked triage rows with descriptive flag labels** — "the flag says
   *what* the anomaly is" (`UPCODING · HCPCS CONSOLIDATION`), risk numeral
   leading each row (feed rows, script Scene 2.2).
2. **The Provider Deep-Dive dossier**: big header (identity + 54px Oxanium
   risk numeral + confidence bar) → a cyan-tinted **"AI ANALYSIS · N ANOMALY
   SIGNALS"** band with per-signal one-liners → uppercase tab strip
   (Signal Explanation / Policy Analysis / Evidence Log / Billing Timeline).
   The script calls this "where the story lives."
3. **Synchronized-signal narrative** — signal descriptions cross-reference
   each other and a trigger event ("both signals exhibit synchronized timing
   with ownership transfer").
4. **Peer comparison** — provider vs p50/p90 bars ("78% vs. 18% peer median").
5. **Policy sections with citations, determination + confidence, recommended
   actions, and the amber "POLICY GAP IDENTIFIED" callout** — "the capability
   nobody else has" (Scene 2.4).
6. **Timeline of detection events** — dated ledger from trigger event through
   AI detection to analyst assignment ("the smoking gun").
7. **Right-side AI panel** as a case partner (long-demo option B).

Items 1, 2, 5, 7 are directly translatable now; 3 arrives with B3's LLM
narrative; 4 and 6 lack backing APIs today (see §6 phase 2).

## 2. Design decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Extend the inline page; retire all three orphan panels.** `InvestigationWorkbenchPage` is restructured in place, extracting *new, purpose-built* components; `EntityDetailPanel`, `EvidencePanel`, `TimelinePanel` (+ CSS modules + their tests) are deleted in U2. | The orphans predate the domain-config display layer: hardcoded English headings, raw `entity.type` badges, raw property keys — each would need a rewrite to satisfy the hard constraint, and `EvidencePanel` duplicates the live `EvidencePackViewer` on an older type. The inline page already has correct data wiring, availability handling, and `domainDisplay` usage — that is the asset worth keeping. The two genuinely good ideas inside the orphans are salvaged, not the files: the Community row concept (subsumed by D4's cluster overlay/membership panel, keeping `communityIdFor`) and the `role="meter"` a11y pattern (folded into `ConfidenceBar` usage guidance). Keeping dead code "in case" would leave two parallel component families to maintain under 8 SP. |
| D2 | **Signature element: the Entity Dossier header + AI signal band.** One place of boldness — an oversized Oxanium risk numeral with confidence bar, over a cyan-tinted band that speaks in the system's voice ("AI ANALYSIS · N RISK SIGNALS") listing each signal with a plain-language rationale. Everything below it stays quiet, disciplined `Card` composition. | This is the exact moment the presenter script milks twice (Scenes 2.2→2.3). The app currently renders risk as a small `RiskBadge` chip — visually equal to a status chip. The dossier header makes "how bad, and why" the first legible fact on the page. Restraint elsewhere keeps U2 feasible and avoids the mockup's inline-style sprawl. |
| D3 | **Tab the dossier: Signals / Network / Policy / Evidence.** The workbench detail area becomes a capability-gated `Tabs` strip (existing `ui/Tabs` component, styled uppercase/underline). Timeline is deliberately **not** a tab in this sprint (no detection-event API — §6). | Mirrors the mockup's deep-dive structure while replacing its long-scroll stack of cards; each tab maps 1:1 to a capability gate (§5), which makes degradation structural instead of scattered conditionals. Tab labels are domain-neutral platform vocabulary (like the existing "Overview/Queue Health"), not domain strings — domain language enters through the data (entity titles, factor names, policy titles). |
| D4 | **Cluster overlay = community-colored nodes + membership panel; predicted links = dashed with confidence.** Node fill switches to community color when cluster data exists (falling back to entity-type color), with the type legend augmented by a cluster legend; a membership panel lists clusters (label, size, anomaly score) and highlights members on hover/select. Predicted links render dashed (`linkLineDash [4,3]`), purple, with confidence in the link tooltip. | Uses `communityIdFor` (already written back onto entities by B1) and `useGnnClusters` (already wired on the dashboard). `force-graph` natively supports `linkLineDash` — no custom canvas painting. Contract gaps (centrality ordering, predicted-link transport) are specified as UI expectations with explicit dependencies in §7, not silently assumed. |
| D5 | **Evidence pack: narrative leads, attribution follows.** `EvidencePackViewer` is reshaped so `pack.reasoning` is the lead element — set larger, in a cyan-tinted narrative band with an "AI narrative" mono eyebrow — followed by a new signed feature-attribution bar section (SHAP), then subgraph, contributing items, and policy citations. | B3 makes `reasoning` an LLM narrative with template fallback; the same field renders either way, so the lead treatment is free of contract risk. The SHAP section is additive and hidden until B3's attribution field lands (§7). |
| D6 | **Alert Feed becomes a risk-ranked triage queue; evidence expansion gets a real subgraph.** Rows lead with the risk numeral and a mono flag label derived from the alert's own data (tags → uppercase, joined with " · "; fallback: top factor name). The expanded `EvidencePackViewer` fetches the alert entity's depth-1 neighborhood instead of receiving an empty subgraph, and passes real `entityTypes` from domain config. | Flag labels are the mockup's cheapest, highest-yield persuasion trick and require zero new backend: `alert.tags` already carries rule-derived slugs. The empty-subgraph pass-through is a live defect of the current page (line 201) — the design fixes the surfacing, not the contract. |
| D7 | **Policy items surface on entity and alert views via client-side filtering.** New `EntityPolicyPanel` filters `usePolicyItems(kb)` by `target_kind`/`target_ref`; alert rows show a severity-tinted policy chip when items reference the alert or its entity, linking to `/policy`. Critical items render an amber "POLICY SIGNAL" callout in the mockup's POLICY GAP style. | `target_kind`/`target_ref` already exist on `PolicyItemSummaryResponse` — this is the one mockup capability (policy grounding next to the evidence) deliverable with zero contract work. |
| D8 | **Reuse the app-shell AI panel; do not build a per-page one.** The dossier keeps its "Ask AI" action (deep-links `buildRagChatUrl` context as today); the right-side companion remains `AiAssistantPanel` toggled by `uiStore.aiPanelOpen`. | The mockup's AI panel already exists in the shell. Duplicating it per-page would burn U2 points on a solved problem. |
| D9 | **Motion: one orchestrated moment, nothing ambient.** Adopt the mockup's `fadeUp` (0.35s ease, 8px rise) on tab-panel mount and dossier-header change only, behind `prefers-reduced-motion`. No pulse rings, no scroll effects. | A single consistent reveal reads as intentional; scattering the mockup's four keyframes across the app reads as template noise and costs e2e stability. |

## 3. Visual direction (usage rules for the existing tokens)

**Type roles** (all faces already loaded in `theme/global.css`):

| Role | Face | Treatment | Where |
|---|---|---|---|
| Display | Oxanium 700–800 | Page titles, tab labels (12px uppercase, 0.07em tracking), **risk numerals** (dossier 44–48px, triage rows 24px, line-height 1) | SectionHeader title, dossier header, triage rows, tabs |
| Eyebrow / data label | IBM Plex Mono 500 | 10–11px, uppercase, 0.07em tracking, `--c-muted` (or accent color when the label speaks for the system, e.g. `AI ANALYSIS`) | Card eyebrows, metric labels, flag labels, entity ids |
| Body | IBM Plex Sans 400 | 13–14px, `--c-text`; secondary copy 12px `--c-dim` | Rationales, narratives, descriptions |

**Color roles** — accents are semantic, never decorative:

- `--c-cyan` — the system's voice (AI bands, narratives, interactive accents,
  focus rings). Anything cyan-tinted is "the platform speaking."
- `--c-red` — confirmed risk: high/critical severity, risk numerals ≥ high
  threshold, positive (risk-raising) attribution bars.
- `--c-amber` — warning/possible: medium severity, policy callouts.
- `--c-green` — cleared/healthy: acknowledged, completed, risk-lowering
  attribution bars.
- `--c-purple` — analytics structure: predicted links, workflow accents.
- Cluster palette: derived series for community coloring (extend
  `ENTITY_COLOR_PALETTE` usage in `graphStyles.ts` with a
  `clusterColorFor(clusterId)` hash — deterministic across renders and packs).

**Tint formula** (the mockup's signature surface treatment): callout surfaces
are `color-mix`/alpha tints of a semantic accent — background at ~6–10%
alpha, border at ~18–30% alpha, on top of `--c-s2`. Codified as three
`pages.css` utility classes (`.callout--ai`, `.callout--warning`,
`.callout--risk`) instead of per-component inline styles.

**Spacing**: 4px base; cards 16–22px padding; section gap 18px; the dossier
column max-width stays fluid (the app shell already owns page chrome).

**Copy rules**: labels come from domain config or the data (factor names,
tags, policy titles). Platform chrome uses domain-neutral vocabulary
("Signals", "Network", "Evidence"). Empty states direct action ("Select an
entity to load its network"), never apologize. The stale "Phase 5 data live"
chip on the dashboard is replaced with the active domain's display name.

## 4. Per-page layouts

### 4.1 Investigation Workbench (`InvestigationWorkbenchPage.tsx`)

Two-zone layout replacing the current vertical stack: a persistent search
rail and the entity dossier. On narrow viewports the rail stacks above the
dossier (existing `investigation-layout` breakpoint pattern).

```
┌ SectionHeader ────────────────────────────────────────────────────────────────┐
│ ENTITY WORKBENCH · {kb.name}                              [alert severity ▸]  │
│ {getEntityTitle(entity, config)}          (Oxanium)                           │
└───────────────────────────────────────────────────────────────────────────────┘
┌ Search rail (~300px) ──────┐ ┌ Dossier column ────────────────────────────────┐
│ KNOWLEDGE BASE   (mono)    │ │ ┌ EntityDossierHeader ───────────────────────┐ │
│ [kb select]                │ │ │ {title}                          ┌───────┐ │ │
│ ENTITY SEARCH              │ │ │ {subtitle} · {type label chip}   │  87   │ │ │
│ [search input]             │ │ │ [chip] [chip] [chip]             │ RISK  │ │ │
│ ┌ results ───────────────┐ │ │ │  (getEntityChips)                │▮▮▮▮▮░ │ │ │
│ │ ▸ {title}              │ │ │ │ [Ask AI]                         └───────┘ │ │
│ │   {type · subtitle}    │ │ │ └────────────────────────────────────────────┘ │
│ │ ▸ …                    │ │ │ ┌ SignalBand (.callout--ai) ─────────────────┐ │
│ └────────────────────────┘ │ │ │ ◆ AI ANALYSIS · {n} RISK SIGNALS   (mono)  │ │
│                            │ │ │ ▸ {factor_name}      ▮▮▮▮░░ {contribution} │ │
│ (rail persists during      │ │ │   {factor.rationale}                       │ │
│  dossier navigation)       │ │ │ ▸ {factor_name}      ▮▮░░░░                │ │
│                            │ │ └────────────────────────────────────────────┘ │
│                            │ │  SIGNALS │ NETWORK │ POLICY │ EVIDENCE  (tabs) │
│                            │ │ ┌ active tab panel ──────────────────────────┐ │
│                            │ │ │              (see below)                   │ │
│                            │ │ └────────────────────────────────────────────┘ │
└────────────────────────────┘ └────────────────────────────────────────────────┘
```

Annotations:

- **EntityDossierHeader** (new): title/subtitle/chips via `domainDisplay.ts`
  only; risk numeral from `useRiskScore` (`overall_score` × 100, Oxanium,
  color-stepped by severity), `ConfidenceBar` beneath; renders without the
  numeral block when `risk_scoring` is off or risk is `unavailable`
  (falls back to the availability reason as a mono sub-line).
- **SignalBand** (new): the risk factors currently in the "Risk factors"
  card, promoted to the signature callout — factor name (mono, accent by
  contribution sign), one-line rationale, signed contribution bar. Factor
  families (peerstats z-scores, `timeseries_anomaly:*`) arrive already
  labeled by the backend; the band renders whatever families exist — this is
  what makes it pack-agnostic.
- **SIGNALS tab**: the anomaly chart (current `ChartFrameInvestigation`,
  extracted to `AnomalyTrendPanel`): `TrendBars` + anomaly chips, with
  anomaly points marked in `--c-red`; below it, the full factor detail list
  (today's risk-factor card content, grouped by family). Gated: `timeseries`
  off → chart section absent; `risk_scoring` unavailable → EmptyState.
- **NETWORK tab**: depth select + `GraphCanvas` with cluster overlay
  (D4) + `ClusterMembershipPanel` (new) beside/below the canvas listing
  clusters (label ?? cluster_id, member count, anomaly chip); selecting a
  cluster highlights members; selecting a node navigates (existing
  behavior). Gated: `gnn` off → overlay + membership panel absent, canvas
  renders exactly as today.
- **POLICY tab**: `EntityPolicyPanel` (new) — `usePolicyItems(kb)` filtered
  to `target_kind === 'entity' && target_ref === entityId`; rows show
  severity chip, title, status, updated-at, link to `/policy`; critical
  items get the amber callout treatment. Gated on `explainability`.
- **EVIDENCE tab**: the reshaped `EvidencePackViewer` (D5) fed by the
  entity's alert as today; when no alert/pack exists, EmptyState pointing at
  the Alert Feed. Gated on `explainability`.
- Tabs with a false capability are **not rendered** (no disabled ghosts);
  the strip collapses to what the pack supports. If only one tab survives,
  the strip is dropped and the surviving panel renders directly.

### 4.2 Dashboard (`DashboardPage.tsx`)

Keeps the 3-tab structure and KPI band; the reshape is hierarchy + live data.

```
┌ SectionHeader ────────────────────────────────────────────────────────────────┐
│ OPERATIONAL OVERVIEW · {domain.display_name}            [{kb.name} chip]      │
│ Dashboard                                                                     │
└───────────────────────────────────────────────────────────────────────────────┘
  OVERVIEW │ QUEUE HEALTH │ POLICY SIGNALS                       (existing Tabs)
┌ KPI band (existing KpiCard × 4, Oxanium values enlarged) ─────────────────────┐
│ [⚠ Active alerts] [🛡 High-risk entities] [◫ Entities monitored] [~ Runs]     │
└───────────────────────────────────────────────────────────────────────────────┘
Overview tab:
┌ Severity Mix (ChartFrame) ─────────────┐ ┌ Lead case card ────────────────────┐
│ TrendBars by severity                  │ │ {lead alert entity_label}    [94]  │
└────────────────────────────────────────┘ │ FLAG: {tags · mono uppercase}      │
                                           │ {reasoning}     [Investigate ▸]    │
                                           └────────────────────────────────────┘
Policy Signals tab:
┌ Top risk entities ─────────┐ ┌ Graph clusters ────────────┐ ┌ Metric Trend ──┐
│ {title via domainDisplay}  │ │ ● {label}  {n} entities    │ │ (ChartFrame)   │
│  … [RiskBadge]             │ │   [anomaly chip]  ▸ open   │ │                │
│ (row links → workbench)    │ │ (● = clusterColorFor swatch│ └────────────────┘
└────────────────────────────┘ │  matching graph overlay)   │
                               └────────────────────────────┘
```

Annotations:

- Overview lead card adopts the triage-row treatment (risk numeral + mono
  flag label from tags) and links into the workbench with `?kb=`.
- Top-risk rows render entity titles through `domainDisplay` when the entity
  is resolvable, falling back to the current `entity_type + id` formatting;
  each row links to `/investigation/{id}?kb=`.
- Graph clusters panel (already wired to `useGnnClusters`) gains the cluster
  color swatch (same `clusterColorFor` as the canvas overlay — one visual
  vocabulary across pages) and a "open in workbench" affordance targeting the
  highest-anomaly member. Panel absent when `gnn` is false; EmptyState only
  when `gnn` is true but no clusters exist yet.
- Stale header copy replaced (§3 copy rules); no structural change to Queue
  Health.

### 4.3 Alert Feed (`AlertFeedPage.tsx`)

```
┌ SectionHeader ──────────────────────────────────────────────┐
│ TRIAGE QUEUE · {n} alerts                                   │
│ Alert Feed                                                  │
└─────────────────────────────────────────────────────────────┘
[ All │ Critical │ High │ Acknowledged ]              (FilterBar, unchanged)
┌ Triage row (Card compact) ──────────────────────────────────────────────────┐
│ ┌────┐  {entity_label}                [severity][status][policy ⚑ if items] │
│ │ 94 │  FLAG: {TAGS · JOINED · UPPERCASE MONO}                              │
│ │RISK│  {reasoning — one line, --c-dim}                                     │
│ └────┘  [Investigate] [Ask AI] [Evidence ▾] [Promote to case] [Ack]         │
│         ▮▮▮▮▮▮▮▮░░ confidence                                               │
└─────────────────────────────────────────────────────────────────────────────┘
  └ expanded (Evidence ▾):
    ┌ EvidencePackViewer (reshaped, D5) ──────────────────────────────────────┐
    │ ◆ AI NARRATIVE (mono eyebrow, .callout--ai)                             │
    │ {pack.reasoning — lead element, 14px}                                   │
    │ FEATURE ATTRIBUTION (when pack.attribution present — §7)                │
    │   {feature}  ▮▮▮▮▮▮ +0.32   (red, risk-raising)                         │
    │   {feature}      ▮▮ −0.08   (green, risk-lowering)                      │
    │ [subgraph: entity depth-1 neighborhood, real entityTypes]               │
    │ Contributing evidence · Policy citations (existing sections, restyled)  │
    └─────────────────────────────────────────────────────────────────────────┘
```

Annotations:

- Risk numeral = `Math.round(alert.confidence * 100)` exactly as the current
  `RiskBadge` (no new semantics — a bigger typographic slot for the same
  number). Flag label from `alert.tags` (already rule-derived); rows without
  tags fall back to the severity word — never an invented domain string.
- The expansion fetches `useInvestigationNeighborhood(alert.knowledge_base_id,
  alert.entity_id, 1)` and passes `domainConfig.entities.map(e => e.name)` —
  fixing the empty-subgraph defect while keeping the existing
  filter-to-pack-nodes logic in the viewer.
- Policy flag chip per D7; absent when `explainability` is false (as is the
  entire Evidence action, since packs come from the explainability engine).

## 5. Capability degradation matrix (hard constraint)

Principle: **capability off ⇒ surface absent; capability on but data
unavailable ⇒ EmptyState/reason** (the existing `availability_status`
pattern). Gates read `useDomainFeatures().data.capabilities` (already
refetched on pack hot-swap via `domainConfigInvalidationKeys`).

| Surface | `gnn: false` (housing today) | `timeseries: false` | `explainability: false` | `peer_stats: false` (housing today) |
|---|---|---|---|---|
| Workbench NETWORK tab | Cluster overlay, cluster legend, membership panel, predicted links all absent; plain type-colored GraphCanvas renders as today | — | — | — |
| Workbench SIGNALS tab | — | Anomaly chart section absent; anomaly chips absent | — | Factor list shows only the families present in the risk profile (no peer z-score rows) — renders whatever the backend produced, no hardcoded family assumptions |
| Workbench POLICY / EVIDENCE tabs | — | — | Tabs not rendered; tab strip collapses | — |
| Dossier header + SignalBand | — | — | — | Band renders present factors; hidden entirely when risk is `unavailable` (reason shown in header sub-line) |
| Dashboard Graph clusters panel | Panel absent (not EmptyState) | — | — | — |
| Dashboard Metric Trend | — | Panel absent | — | — |
| Alert Feed evidence expansion + policy chips | Subgraph section falls back exactly as viewer does today | — | "View evidence" action and policy chips absent | — |
| Whole pages | Nav/route gating unchanged — `Sidebar`/`AppShell` already hide/redirect pages per pack nav + role `enabled_pages` (housing routes none of these three pages; that continues to work with zero reshape involvement) | | | |

Housing verification bar for U2: switch to the housing pack (`make dev-domain
DOMAIN=department_air_force_housing`), confirm its four routed pages render
untouched, then visit the reshaped pages under a pack state where they are
routed (CMS) and under capability-off simulation — no CMS strings, no crashed
gates, entity titles/chips from `display_fields` throughout.

## 6. Scope: in-sprint vs phase 2

**In U2 (8 SP)** — everything in §4 plus the D1 deletions. Feasibility rests
on: tokens already exist; `Tabs`/`Card`/`Chip`/`ConfidenceBar` are reused;
cluster overlay reads properties B1 already writes back; policy panels are
client-side filters; the evidence-subgraph fix is a two-prop change plus one
hook call.

**Phase 2 / out of sprint** (record in `docs/backlog/frontend.md` at U2
closeout):

- **Timeline tab** — needs a detection-events source (alert history + policy
  item transitions + anomaly `detected_at` exist in separate stores; no
  unified feed API). The mockup's "smoking gun" ledger is a backend story
  first.
- **Peer-comparison bar chart** (entity vs p50/p90) — peerstats persists
  z-scores as signals, not peer distributions; needs a peer-distribution
  endpoint.
- **Cluster centrality ordering in the membership panel** — until
  `centrality_score` is exposed on cluster members via the clusters route
  (or resolvable cheaply from entity properties for all members), the panel
  orders by anomaly score and member count only.
- **Case Management / Policy Intelligence page reshapes** — out of U1's
  three-page mandate; they inherit the token usage rules for free where they
  already use the shared kit.
- Any graph-canvas performance work at >1% TN scale (frontend.15, unchanged).

## 7. Contract dependencies (UI expectation specified now; consumed as B-track lands)

| UI surface | Expectation | Contract state (verified) | Depends on |
|---|---|---|---|
| Predicted links (dashed, confidence) | Relationships in subgraph responses distinguishable as predicted, with confidence: preferred transport is relationship `metadata.predicted: true` + `metadata.confidence` via B1's analytics write-back (renders through the existing neighborhood fetch, no new endpoint); alternative is a predicted-links list on the clusters route. `GraphCanvas` styles by `linkLineDash([4,3])`, `--c-purple`, confidence in the link tooltip. | `ClusterResult` = `cluster_id`/`anomaly_score`/`entity_ids`/`label` only; no predicted-link shape anywhere in `schema.ts` | B1 write-back shape confirmation at U2 start; if absent, ship overlay + membership panel and land dashed links when the transport exists |
| Cluster membership centrality sort | Members ordered by `centrality_score` | Not on `ClusterResult`; B1 writes it onto entities, but the membership panel only has ids | Phase 2 unless exposed (see §6) |
| SHAP attribution bars | `pack.attribution: list of {feature_name, contribution (signed), …}` rendered as signed horizontal bars (red = risk-raising, green = risk-lowering), sorted by \|contribution\| | `EvidencePackResponse` has no attribution field (landed with B3 — `attribution` + `narrative_sections` now in `schema.ts`, optional) | **B3 (BL-048)** — section hidden until the field exists; regen contracts + codegen when it lands |
| LLM narrative lead | `pack.reasoning` (unchanged field) | Already present | None — B3 upgrades the content, not the shape |
| Cluster overlay node coloring | `community_id` on entity properties/metadata (`communityIdFor`) | B1 write-back live | None |
| Policy on entity/alert views | `target_kind`/`target_ref` filtering | Already present | None |

## 8. Component inventory

**Reuse unchanged**: `ui/Card`, `ui/Chip`, `ui/ConfidenceBar`, `ui/RiskBadge`
(dashboard/list contexts), `ui/KpiCard`, `ui/SectionHeader`, `ui/Tabs`,
`ui/FilterBar`, `ui/EmptyState|ErrorState|LoadingState`, `charts/TrendBars`,
`charts/ChartFrame`, `layout/AiAssistantPanel` + `stores/uiStore.aiPanelOpen`,
`layout/Sidebar|TopBar`, `common/toastStore`.

**Modify**:

| File | Change |
|---|---|
| `src/pages/InvestigationWorkbenchPage.tsx` | Restructure per §4.1: search rail + dossier + capability-gated tabs; extract inline pieces into the new components below |
| `src/pages/AlertFeedPage.tsx` | Triage-row treatment; neighborhood fetch + real `entityTypes` for the evidence expansion; policy flag chips |
| `src/pages/DashboardPage.tsx` | Header copy; lead-case flag treatment; cluster swatches + workbench links; capability-gated panel presence |
| `src/components/investigation/EvidencePackViewer.tsx` | Narrative lead band; attribution section (gated on field presence); restyled citations |
| `src/components/investigation/GraphCanvas.tsx` | Community-colored nodes (fallback: type color), cluster legend rows, dashed predicted links via `linkLineDash`, tooltip confidence |
| `src/utils/graphStyles.ts` | `clusterColorFor(clusterId)` (deterministic hash palette), predicted-link style constants; `communityIdFor` gains its first live consumer |
| `src/pages/pages.css` | New classes: `.workbench-layout`, `.workbench-rail`, `.dossier-header`, `.dossier-risk`, `.signal-band`, `.triage-row`, `.callout--ai|--warning|--risk`, `.flag-label`; `fadeUp` keyframe + `prefers-reduced-motion` guard |
| `src/components/ui/ui.css` | Only if chip tint variants need one addition; otherwise untouched |

**New** (all under existing directories, styled via `pages.css` semantic
classes — no Tailwind, no new CSS modules):

| File | Responsibility |
|---|---|
| `src/components/investigation/EntityDossierHeader.tsx` | §4.1 header: domainDisplay identity + risk numeral + confidence; availability-aware |
| `src/components/investigation/SignalBand.tsx` | AI-voice callout listing risk factors with signed bars |
| `src/components/investigation/AnomalyTrendPanel.tsx` | Extracted/renamed `ChartFrameInvestigation` with red anomaly markers |
| `src/components/investigation/ClusterMembershipPanel.tsx` | Cluster list + member highlight interplay with GraphCanvas |
| `src/components/investigation/EntityPolicyPanel.tsx` | Policy items filtered by `target_kind`/`target_ref`; critical callout |
| `src/components/charts/AttributionBars.tsx` | Signed horizontal attribution bars (SHAP section; reused wherever attribution appears later) |

**Delete** (D1): `src/components/investigation/EntityDetailPanel.tsx` +
`.module.css`, `EvidencePanel.tsx` + `.module.css`, `TimelinePanel.tsx`, and
their `__tests__` entries.

## 9. U2 implementation checklist (AC → files)

BL-050 acceptance items mapped; each lands with Vitest coverage and a
full-stack Playwright spec (`make dev`, no `page.route` mocks of the subject
under test; `/api/`-anchored route patterns only where auxiliary mocking is
unavoidable per the CLAUDE.md gotcha).

1. **Cluster overlays + membership on GraphCanvas** — `GraphCanvas.tsx`,
   `graphStyles.ts`, `ClusterMembershipPanel.tsx`,
   `InvestigationWorkbenchPage.tsx` (NETWORK tab), `pages.css`. E2e: CMS pack,
   entity with `community_id`, overlay + panel visible; housing-style
   `gnn:false` state shows plain canvas.
2. **Dashed predicted links w/ confidence** — `GraphCanvas.tsx`,
   `graphStyles.ts`; gated on §7 transport confirmation at story start.
3. **SHAP bars + LLM narrative in evidence viewer** — `EvidencePackViewer.tsx`,
   `AttributionBars.tsx`; contract regen + `npm run codegen:api` when B3's
   field lands; narrative-lead treatment ships regardless.
4. **Policy items on entity/alert views** — `EntityPolicyPanel.tsx`,
   `InvestigationWorkbenchPage.tsx` (POLICY tab), `AlertFeedPage.tsx` chips.
5. **Anomaly markers on the timeseries chart** — `AnomalyTrendPanel.tsx`
   (B2's pipeline anomalies already flow through the unchanged
   `EntityTimeseriesResponse`).
6. **Dashboard clusters panel live** — `DashboardPage.tsx` (+ swatches/links).
7. **Workbench/alert-feed/dashboard reshape** — the page files + `pages.css`
   per §4; orphan deletions; browser verification on both packs per §5.
8. **Gates** — `tsc -b` clean, ESLint clean, Vitest green, Playwright e2e per
   surfaced capability against the full stack, no hand-written wire DTOs.

## 10. Risks

- **8 SP pressure.** Mitigation: §6 phase-2 fence is explicit; items 1/3/4/5/6
  of §9 are independent and can land incrementally; the tab structure means a
  slipping tab degrades to "absent", not "broken".
- **B3 timing vs item 3.** The attribution section is presence-gated on the
  response field, so the viewer reshape merges before B3 without a dead
  section; only the codegen step waits.
- **Predicted-link transport ambiguity** (§7). Resolved by a 15-minute
  code-check at U2 start against B1's write-back; both candidate transports
  are designed for, neither blocks the rest of the NETWORK tab.
- **Canvas readability with two color systems** (type color vs community
  color). Mitigation: community color replaces type color only when overlay
  mode is active (legend switches with it) — never both at once.
- **pages.css growth.** New classes are namespaced (`.workbench-*`,
  `.dossier-*`, `.triage-*`, `.callout--*`) and the three orphan CSS modules
  are deleted, keeping net stylesheet growth small.
- **Pack hot-swap regressions.** Capability gates read the same queries the
  swap flow already invalidates (`domainConfigInvalidationKeys`), and the §5
  housing check is part of U2's browser verification, not an afterthought.
