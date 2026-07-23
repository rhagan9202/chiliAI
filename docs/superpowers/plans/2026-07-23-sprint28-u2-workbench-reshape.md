# Sprint 2026-28 U2 — Workbench Reshape Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the U1 workbench reshape design (BL-050): entity dossier with AI signal band and capability-gated tabs, cluster overlays + membership on the graph canvas, narrative-lead + SHAP-attribution evidence viewer, risk-ranked triage rows, policy surfacing on entity/alert views, and live dashboard clusters — IntegrityAI hierarchy on the existing token system.

**Architecture:** Restructure the three workbench pages in place, extracting six new purpose-built components under existing directories; delete the three orphan investigation panels (D1). All labels flow through `domainDisplay.ts` + domain config; every new surface is gated by `useDomainFeatures().data.capabilities` (capability off ⇒ surface absent; on-but-unavailable ⇒ EmptyState/reason). Design: `docs/superpowers/specs/2026-07-23-sprint28-u1-workbench-reshape-design.md`.

**Tech Stack:** React 19 + TypeScript strict, Vite 8, TanStack Query, zustand, react-force-graph-2d, Vitest + Testing Library, Playwright.

## Global Constraints

- Frontend only. **No backend changes, no contract regen** — `EvidencePackResponse.attribution?: FeatureAttributionResponse[]` and `narrative_sections?: NarrativeSectionResponse[]` already exist in `src/lib/api/schema.ts` (landed with B3); consume them as optional fields. Never hand-write wire DTOs; import from `src/api/contracts.ts` / generated schema.
- **Predicted-link transport is absent** (verified 2026-07-23: `agent/coordinator.py` never reads `GnnAnalysisResponse.predicted_links`; relationships carry no `metadata.predicted`). Ship the canvas support + style constants dormant — render dashed links only when a relationship's `metadata.predicted === true` — and do NOT fabricate data. Task 10 records the backend dependency in `docs/backlog/frontend.md`.
- Domain-config hard constraint: no hardcoded domain strings anywhere new. Entity identity via `getEntityTitle/Subtitle/Chips/TypeLabel(entity, config)`; platform chrome uses domain-neutral vocabulary (Signals / Network / Policy / Evidence).
- Capability gates: `gnn` → cluster overlay/membership/dashboard clusters panel; `timeseries` → anomaly chart; `explainability` → Policy + Evidence tabs, evidence actions, policy chips; `risk_scoring` unavailable → dossier renders identity without the numeral block (availability reason as mono sub-line). Tabs with a false capability are NOT rendered (no disabled ghosts); if only one tab survives, drop the strip and render the panel directly.
- Styling: semantic classes in `src/pages/pages.css` only (namespaced `.workbench-*`, `.dossier-*`, `.triage-*`, `.signal-band`, `.callout--ai|--warning|--risk`, `.flag-label`); tokens from `theme/global.css` (`--c-cyan` = system voice, `--c-red` = confirmed risk, `--c-amber` = warning/policy, `--c-green` = cleared/lowering, `--c-purple` = analytics structure). No Tailwind, no new CSS modules, no inline style objects except dynamic values (bar widths, swatch colors).
- Motion: exactly one `fadeUp` keyframe (0.35s ease, 8px rise) on tab-panel mount and dossier-header change, inside `@media (prefers-reduced-motion: no-preference)`. Nothing ambient.
- Gates per task: `npm run test:run` (Vitest), and at closeout `npm run build` (tsc -b + vite) + `npm run lint`. TypeScript strict — no `any`, no unused locals/params. Playwright e2e (Task 11) runs against the FULL stack (`make dev`, real API) — never `page.route`-mock the subject under test; `/api/`-anchored patterns only for unavoidable auxiliary mocking.
- All commands from `chili_app/` unless stated. Commit messages end `(U2)`.
- Interface contracts used throughout (verified 2026-07-23): `Tabs` props `{activeTabId, ariaControlsPrefix?, idPrefix?, onChange, tabs: {id,label}[]}`; `ConfidenceBar` `{color?, value /* 0-100 */}`; `RiskBadge` `{score /* 0-100 */}`; `useRiskScore(kb, entityId)` → `RiskScoreResponse{availability_status, overall_score, risk_level, factors[{factor_name, contribution, rationale?}], unavailable_reason}`; `useGnnClusters(kb)` → `{clusters?: [{cluster_id, anomaly_score, entity_ids?, label?}]}`; `usePolicyItems(kb, status?)` → `PolicyItemListResponse`; `useInvestigationNeighborhood(kb, entityId, depth)` → `{entities, relationships}`; `useDomainFeatures()` → `{capabilities}`; `communityIdFor(entity)` → `string|null`; `colorForEntityType(type, knownTypes)`; `riskScoreFor(entity)`; `buildRagChatUrl(ctx)`.

---

### Task 1: Foundation — pages.css classes + graphStyles cluster/predicted utilities

**Files:**
- Modify: `chili_app/src/utils/graphStyles.ts` (append after `communityIdFor`, ~line 60)
- Modify: `chili_app/src/pages/pages.css` (append at end)
- Test: create `chili_app/src/utils/__tests__/graphStyles.test.ts`

**Interfaces:**
- Produces: `clusterColorFor(clusterId: string): string` (deterministic hash into `CLUSTER_COLOR_PALETTE`), `CLUSTER_COLOR_PALETTE: readonly string[]`, `PREDICTED_LINK_COLOR = 'rgba(168, 85, 247, 0.75)'`, `PREDICTED_LINK_DASH: readonly [number, number] = [4, 3]`, `isPredictedRelationship(rel: Relationship): boolean` (reads `metadata.predicted === true`), `predictedConfidenceFor(rel: Relationship): number | null` (reads `metadata.confidence`, clamped [0,1], null when absent/non-numeric). Consumed by Tasks 6, 9.
- Produces CSS classes consumed by every later task: `.workbench-layout`, `.workbench-rail`, `.dossier-header`, `.dossier-header__identity`, `.dossier-risk`, `.dossier-risk__numeral`, `.dossier-risk__label`, `.signal-band`, `.signal-band__row`, `.signal-band__bar`, `.triage-row`, `.triage-row__numeral`, `.flag-label`, `.callout--ai`, `.callout--warning`, `.callout--risk`, `.cluster-swatch`, `.fade-up`.

- [ ] **Step 1: Write the failing tests** — create `src/utils/__tests__/graphStyles.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import type { Relationship } from '../../api/contracts'
import {
  CLUSTER_COLOR_PALETTE,
  clusterColorFor,
  isPredictedRelationship,
  PREDICTED_LINK_COLOR,
  PREDICTED_LINK_DASH,
  predictedConfidenceFor,
} from '../graphStyles'

function rel(metadata: Record<string, unknown>): Relationship {
  return {
    id: 'rel-1',
    type: 'refers',
    source_id: 'a',
    target_id: 'b',
    properties: {},
    metadata,
    created_at: '2026-07-23T00:00:00Z',
    version: 1,
  } as Relationship
}

describe('clusterColorFor', () => {
  it('is deterministic for the same cluster id', () => {
    expect(clusterColorFor('community-5')).toBe(clusterColorFor('community-5'))
  })

  it('returns a palette color', () => {
    expect(CLUSTER_COLOR_PALETTE).toContain(clusterColorFor('community-5'))
  })

  it('spreads distinct ids across the palette', () => {
    const colors = new Set(
      ['c-1', 'c-2', 'c-3', 'c-4', 'c-5', 'c-6', 'c-7', 'c-8'].map(clusterColorFor),
    )
    expect(colors.size).toBeGreaterThan(1)
  })
})

describe('predicted relationship helpers', () => {
  it('detects metadata.predicted === true only', () => {
    expect(isPredictedRelationship(rel({ predicted: true }))).toBe(true)
    expect(isPredictedRelationship(rel({ predicted: 'yes' }))).toBe(false)
    expect(isPredictedRelationship(rel({}))).toBe(false)
  })

  it('clamps confidence to [0,1] and rejects non-numbers', () => {
    expect(predictedConfidenceFor(rel({ confidence: 0.8 }))).toBe(0.8)
    expect(predictedConfidenceFor(rel({ confidence: 7 }))).toBe(1)
    expect(predictedConfidenceFor(rel({ confidence: 'high' }))).toBeNull()
    expect(predictedConfidenceFor(rel({}))).toBeNull()
  })

  it('exports the dormant predicted-link style constants', () => {
    expect(PREDICTED_LINK_DASH).toEqual([4, 3])
    expect(PREDICTED_LINK_COLOR).toContain('168, 85, 247')
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npm run test:run -- src/utils/__tests__/graphStyles.test.ts`
Expected: FAIL — `clusterColorFor` (and the other new names) not exported.

- [ ] **Step 3: Implement** — append to `src/utils/graphStyles.ts` (reuse the file's existing private `fnv1aHash` and `clamp01`; if `clamp01` is named differently, reuse whatever the file's [0,1] clamp helper is):

```ts
/** Distinct from ENTITY_COLOR_PALETTE so the two color systems never collide. */
export const CLUSTER_COLOR_PALETTE: readonly string[] = [
  '#00d4ff',
  '#a855f7',
  '#f59e0b',
  '#10b981',
  '#f43f5e',
  '#818cf8',
  '#f97316',
  '#2dd4bf',
]

export function clusterColorFor(clusterId: string): string {
  return CLUSTER_COLOR_PALETTE[fnv1aHash(clusterId) % CLUSTER_COLOR_PALETTE.length]
}

/** Dormant until the backend writes predicted-link metadata (see plan Global Constraints). */
export const PREDICTED_LINK_COLOR = 'rgba(168, 85, 247, 0.75)'
export const PREDICTED_LINK_DASH: readonly [number, number] = [4, 3]

export function isPredictedRelationship(relationship: Relationship): boolean {
  return relationship.metadata?.predicted === true
}

export function predictedConfidenceFor(relationship: Relationship): number | null {
  const raw = relationship.metadata?.confidence
  if (typeof raw !== 'number' || Number.isNaN(raw)) {
    return null
  }
  return clamp01(raw)
}
```

Add the `Relationship` import at the top of `graphStyles.ts` alongside the existing `Entity` import (both come from `../api/contracts`).

- [ ] **Step 4: Run tests to verify pass**

Run: `npm run test:run -- src/utils/__tests__/graphStyles.test.ts`
Expected: PASS (all 6).

- [ ] **Step 5: Append the CSS layer** — add to the end of `src/pages/pages.css` (before the responsive `@media` blocks if the file ends with them; otherwise at end — then extend the EXISTING narrow-width media block that stacks `.investigation-layout` with the `.workbench-layout` rule shown at the bottom):

```css
/* ── U2 workbench reshape ─────────────────────────────────────────── */

.workbench-layout {
  display: grid;
  grid-template-columns: minmax(260px, 300px) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.workbench-rail {
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: sticky;
  top: 16px;
}

.dossier-header {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
}

.dossier-header__identity {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.dossier-risk {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 96px;
  padding: 10px 14px;
  border: 1px solid var(--c-b1);
  border-radius: 8px;
  background: var(--c-s2);
}

.dossier-risk__numeral {
  font-family: var(--font-display);
  font-weight: 800;
  font-size: 46px;
  line-height: 1;
}

.dossier-risk__label,
.flag-label {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--c-muted);
}

.callout--ai,
.callout--warning,
.callout--risk {
  border-radius: 8px;
  padding: 14px 16px;
}

.callout--ai {
  background: color-mix(in srgb, var(--c-cyan) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-cyan) 24%, transparent);
}

.callout--warning {
  background: color-mix(in srgb, var(--c-amber) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-amber) 26%, transparent);
}

.callout--risk {
  background: color-mix(in srgb, var(--c-red) 7%, transparent);
  border: 1px solid color-mix(in srgb, var(--c-red) 24%, transparent);
}

.signal-band {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.signal-band__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 140px;
  gap: 12px;
  align-items: center;
}

.signal-band__bar {
  height: 6px;
  border-radius: 3px;
  background: var(--c-s3);
  overflow: hidden;
}

.triage-row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.triage-row__numeral {
  font-family: var(--font-display);
  font-weight: 800;
  font-size: 24px;
  line-height: 1;
  min-width: 52px;
  text-align: center;
  padding: 8px 6px;
  border: 1px solid var(--c-b1);
  border-radius: 6px;
  background: var(--c-s2);
}

.cluster-swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex-shrink: 0;
}

@media (prefers-reduced-motion: no-preference) {
  @keyframes fade-up {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .fade-up {
    animation: fade-up 0.35s ease;
  }
}
```

And inside the existing narrow-viewport media query that already collapses `.investigation-layout` to one column (~line 999–1049):

```css
  .workbench-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .workbench-rail {
    position: static;
  }
```

- [ ] **Step 6: Gates + commit**

Run: `npm run test:run -- src/utils/__tests__/graphStyles.test.ts` then `npm run build` (tsc catches the new imports).
Expected: PASS / build green.

```bash
git add src/utils/graphStyles.ts src/utils/__tests__/graphStyles.test.ts src/pages/pages.css
git commit -m "feat(ui): cluster/predicted graph styles + reshape CSS foundation (U2)"
```

---

### Task 2: EntityDossierHeader + SignalBand

**Files:**
- Create: `chili_app/src/components/investigation/EntityDossierHeader.tsx`
- Create: `chili_app/src/components/investigation/SignalBand.tsx`
- Test: create `chili_app/src/components/investigation/__tests__/EntityDossierHeader.test.tsx`, `chili_app/src/components/investigation/__tests__/SignalBand.test.tsx`

**Interfaces:**
- Consumes: `.dossier-*`, `.callout--ai`, `.signal-band*`, `.flag-label`, `.fade-up` (Task 1); `getEntityTitle/Subtitle/Chips/TypeLabel` from `../../utils/domainDisplay`; `ConfidenceBar`, `Chip` from `../ui`.
- Produces:
  - `EntityDossierHeader` props: `{ entity: RuntimeEntity; config: DomainConfig; riskScore: RiskScoreResponse | null; riskUnavailableReason: string | null; onAskAi: () => void }` — Task 7 consumes.
  - `SignalBand` props: `{ factors: RiskFactorResponse[] }` — Task 7 consumes.

- [ ] **Step 1: Write the failing tests.** `EntityDossierHeader.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { DomainConfig, RiskScoreResponse, RuntimeEntity } from '../../../api/contracts'
import { EntityDossierHeader } from '../EntityDossierHeader'

const config = {
  name: 'medicare_fraud',
  display_name: 'Medicare Fraud Detection',
  entities: [{ name: 'provider', display_label: 'Provider', icon: 'shield', properties: {} }],
  relationships: [],
  ui: {
    display_fields: {
      provider: { title: 'npi', subtitle: 'specialty', chips: ['state'] },
    },
  },
} as unknown as DomainConfig

const entity = {
  id: 'provider:1',
  type: 'provider',
  properties: { npi: '1234567890', specialty: 'Internal Medicine', state: 'TN' },
  metadata: {},
} as unknown as RuntimeEntity

const risk: RiskScoreResponse = {
  entity_id: 'provider:1',
  overall_score: 0.87,
  risk_level: 'high',
  factors: [],
  availability_status: 'available',
  unavailable_reason: null,
}

describe('EntityDossierHeader', () => {
  it('renders identity through domainDisplay and the risk numeral', () => {
    render(
      <EntityDossierHeader
        config={config}
        entity={entity}
        onAskAi={vi.fn()}
        riskScore={risk}
        riskUnavailableReason={null}
      />,
    )
    expect(screen.getByText('1234567890')).toBeInTheDocument()
    expect(screen.getByText('87')).toBeInTheDocument()
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '87')
  })

  it('omits the numeral block and shows the reason when risk is unavailable', () => {
    render(
      <EntityDossierHeader
        config={config}
        entity={entity}
        onAskAi={vi.fn()}
        riskScore={null}
        riskUnavailableReason="No risk profile has been generated for this entity."
      />,
    )
    expect(screen.queryByRole('meter')).not.toBeInTheDocument()
    expect(
      screen.getByText('No risk profile has been generated for this entity.'),
    ).toBeInTheDocument()
  })
})
```

`SignalBand.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { RiskFactorResponse } from '../../../api/contracts'
import { SignalBand } from '../SignalBand'

const factors: RiskFactorResponse[] = [
  {
    factor_name: 'timeseries_anomaly:weekly_carrier_billing_self',
    contribution: 0.4,
    rationale: 'self-history anomaly z=4.5',
  },
  { factor_name: 'weekly_carrier_billing', contribution: 0.0, rationale: 'z=-0.2 vs peers' },
]

describe('SignalBand', () => {
  it('announces the signal count in the AI voice and lists every factor', () => {
    render(<SignalBand factors={factors} />)
    expect(screen.getByText(/AI ANALYSIS · 2 RISK SIGNALS/)).toBeInTheDocument()
    expect(screen.getByText('timeseries anomaly:weekly carrier billing self')).toBeInTheDocument()
    expect(screen.getByText('self-history anomaly z=4.5')).toBeInTheDocument()
  })

  it('renders nothing for an empty factor list', () => {
    const { container } = render(<SignalBand factors={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `npm run test:run -- src/components/investigation/__tests__/EntityDossierHeader.test.tsx src/components/investigation/__tests__/SignalBand.test.tsx`
Expected: FAIL — modules don't exist.

- [ ] **Step 3: Implement `EntityDossierHeader.tsx`:**

```tsx
import type { DomainConfig, RiskScoreResponse, RuntimeEntity } from '../../api/contracts'
import {
  getEntityChips,
  getEntitySubtitle,
  getEntityTitle,
  getEntityTypeLabel,
} from '../../utils/domainDisplay'
import { Chip } from '../ui/Chip'

export interface EntityDossierHeaderProps {
  entity: RuntimeEntity
  config: DomainConfig
  riskScore: RiskScoreResponse | null
  riskUnavailableReason: string | null
  onAskAi: () => void
}

const RISK_COLORS: Record<string, string> = {
  critical: 'var(--c-red)',
  high: 'var(--c-red)',
  medium: 'var(--c-amber)',
  low: 'var(--c-green)',
}

export function EntityDossierHeader({
  entity,
  config,
  riskScore,
  riskUnavailableReason,
  onAskAi,
}: EntityDossierHeaderProps) {
  const subtitle = getEntitySubtitle(entity, config)
  const numeral = riskScore ? Math.round(riskScore.overall_score * 100) : null
  return (
    <div className="dossier-header fade-up" data-testid="entity-dossier-header">
      <div className="dossier-header__identity">
        <h2>{getEntityTitle(entity, config)}</h2>
        <span className="flag-label">
          {getEntityTypeLabel(entity.type, config)}
          {subtitle ? ` · ${subtitle}` : ''}
        </span>
        <div className="alert-row-card__meta">
          {getEntityChips(entity, config).map((chip) => (
            <Chip key={chip} label={chip} tone="info" />
          ))}
        </div>
        <div>
          <button className="button" onClick={onAskAi} type="button">
            Ask AI
          </button>
        </div>
        {riskUnavailableReason ? (
          <span className="flag-label">{riskUnavailableReason}</span>
        ) : null}
      </div>
      {numeral !== null && riskScore ? (
        <div className="dossier-risk">
          <span
            className="dossier-risk__numeral"
            style={{ color: RISK_COLORS[riskScore.risk_level] ?? 'var(--c-text)' }}
          >
            {numeral}
          </span>
          <span className="dossier-risk__label">{riskScore.risk_level} risk</span>
          <div
            aria-label="Composite risk"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={numeral}
            role="meter"
            className="signal-band__bar"
            style={{ width: '72px' }}
          >
            <div
              style={{
                width: `${numeral}%`,
                height: '100%',
                background: RISK_COLORS[riskScore.risk_level] ?? 'var(--c-cyan)',
              }}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}
```

Note: if the codebase's button class differs (check an existing "Ask AI" button in `InvestigationWorkbenchPage.tsx` and reuse its exact classes/markup), match the existing idiom rather than inventing one.

- [ ] **Step 4: Implement `SignalBand.tsx`:**

```tsx
import type { RiskFactorResponse } from '../../api/contracts'

export interface SignalBandProps {
  factors: RiskFactorResponse[]
}

export function SignalBand({ factors }: SignalBandProps) {
  if (factors.length === 0) {
    return null
  }
  return (
    <div className="callout--ai signal-band" data-testid="signal-band">
      <span className="flag-label" style={{ color: 'var(--c-cyan)' }}>
        ◆ AI ANALYSIS · {factors.length} RISK SIGNAL{factors.length === 1 ? '' : 'S'}
      </span>
      {factors.map((factor) => {
        const magnitude = Math.min(100, Math.round(Math.abs(factor.contribution) * 100))
        const raising = factor.contribution >= 0
        return (
          <div className="signal-band__row" key={factor.factor_name}>
            <div>
              <strong>{factor.factor_name.replace(/_/g, ' ')}</strong>
              <div className="metric-row__label">
                {factor.rationale ?? 'No rationale provided.'}
              </div>
            </div>
            <div className="signal-band__bar" title={`${factor.contribution.toFixed(2)}`}>
              <div
                style={{
                  width: `${magnitude}%`,
                  height: '100%',
                  background: raising ? 'var(--c-red)' : 'var(--c-green)',
                }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 5: Run tests to verify pass**

Run: `npm run test:run -- src/components/investigation/__tests__/EntityDossierHeader.test.tsx src/components/investigation/__tests__/SignalBand.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/components/investigation/EntityDossierHeader.tsx src/components/investigation/SignalBand.tsx src/components/investigation/__tests__/EntityDossierHeader.test.tsx src/components/investigation/__tests__/SignalBand.test.tsx
git commit -m "feat(ui): entity dossier header + AI signal band (U2)"
```

---

### Task 3: AnomalyTrendPanel (extract ChartFrameInvestigation, red anomaly markers)

**Files:**
- Create: `chili_app/src/components/investigation/AnomalyTrendPanel.tsx`
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx` (delete the inline `ChartFrameInvestigation` at ~421-444; replace its use at ~274 with the new component — the full page restructure happens in Task 7, this task is a pure extraction that keeps the page green)
- Test: create `chili_app/src/components/investigation/__tests__/AnomalyTrendPanel.test.tsx`

**Interfaces:**
- Consumes: `EntityTimeseriesResponse` from contracts; `TrendBars`, `ChartFrame` idioms from `../charts`; existing anomaly-chip markup from the current page (copy it verbatim into the panel).
- Produces: `AnomalyTrendPanel` props `{ timeseries: EntityTimeseriesResponse | null; unavailableReason: string | null }` — Task 7 consumes.

- [ ] **Step 1: Read the current inline component** (`InvestigationWorkbenchPage.tsx:421-444` and the anomaly-chip rendering near its use at ~274) — the extraction must preserve its exact rendering including `TrendBars` wiring and availability handling.

- [ ] **Step 2: Write the failing test** — `AnomalyTrendPanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { EntityTimeseriesResponse } from '../../../api/contracts'
import { AnomalyTrendPanel } from '../AnomalyTrendPanel'

const timeseries: EntityTimeseriesResponse = {
  entity_id: 'provider:1',
  metric_name: 'weekly_carrier_billing_self',
  points: [
    { timestamp: '2026-01-05T00:00:00Z', value: 10, label: 'Jan 05', is_anomaly: false },
    { timestamp: '2026-01-12T00:00:00Z', value: 60, label: 'Jan 12', is_anomaly: true },
  ],
  availability_status: 'available',
  unavailable_reason: null,
}

describe('AnomalyTrendPanel', () => {
  it('renders the chart and an anomaly chip per anomalous point', () => {
    render(<AnomalyTrendPanel timeseries={timeseries} unavailableReason={null} />)
    expect(screen.getByText(/JAN 12 ANOMALY/i)).toBeInTheDocument()
  })

  it('renders an empty state with the reason when unavailable', () => {
    render(
      <AnomalyTrendPanel
        timeseries={null}
        unavailableReason="No time series is configured or populated for this entity."
      />,
    )
    expect(
      screen.getByText('No time series is configured or populated for this entity.'),
    ).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run to verify failure** — `npm run test:run -- src/components/investigation/__tests__/AnomalyTrendPanel.test.tsx` → FAIL (module missing).

- [ ] **Step 4: Implement** — move the JSX of `ChartFrameInvestigation` plus the page's anomaly-chip block into `AnomalyTrendPanel.tsx` unchanged except: (a) props per the interface above; (b) anomaly chips get `className="flag-label"` styling with `color: 'var(--c-red)'`; (c) the unavailable branch renders the existing `EmptyState` with `unavailableReason ?? 'Select an entity to load its trend.'`. Keep `TrendBars` usage byte-identical. Update the page to import and render `<AnomalyTrendPanel timeseries={...} unavailableReason={...} />` where `ChartFrameInvestigation` was used, deleting the inline definition.

- [ ] **Step 5: Run the panel test + the page's existing tests**

Run: `npm run test:run -- src/components/investigation/__tests__/AnomalyTrendPanel.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`
Expected: PASS — the page tests are the behavior-preservation gate for this extraction; do not weaken them.

- [ ] **Step 6: Commit**

```bash
git add src/components/investigation/AnomalyTrendPanel.tsx src/components/investigation/__tests__/AnomalyTrendPanel.test.tsx src/pages/InvestigationWorkbenchPage.tsx
git commit -m "refactor(ui): extract AnomalyTrendPanel with red anomaly markers (U2)"
```

---

### Task 4: EntityPolicyPanel + AttributionBars

**Files:**
- Create: `chili_app/src/components/investigation/EntityPolicyPanel.tsx`
- Create: `chili_app/src/components/charts/AttributionBars.tsx`
- Test: create `chili_app/src/components/investigation/__tests__/EntityPolicyPanel.test.tsx`, `chili_app/src/components/charts/__tests__/AttributionBars.test.tsx`

**Interfaces:**
- Consumes: `usePolicyItems(kb)` (`../../api/policy`), `PolicyItemSummaryResponse` (fields incl. `id`, `title`, `severity`, `status`, `target_kind: 'entity'|'alert'|'metric'`, `target_ref`, `updated_at`); `FeatureAttributionResponse {feature_name, contribution, rationale}`.
- Produces:
  - `EntityPolicyPanel` props `{ knowledgeBaseId: string | null; targetKind: 'entity' | 'alert'; targetRef: string | null }` — Task 7 (POLICY tab) consumes; Task 8 reuses the same filtering helper for chips.
  - Exported helper `policyItemsForTarget(items: PolicyItemSummaryResponse[], targetKind: 'entity' | 'alert', targetRef: string): PolicyItemSummaryResponse[]` — Task 8 consumes.
  - `AttributionBars` props `{ attribution: FeatureAttributionResponse[] }` — Task 5 consumes. Sorted by |contribution| desc; positive bars red (risk-raising), negative green (risk-lowering); signed value label (`+0.33` / `−0.08`).

- [ ] **Step 1: Write the failing tests.** `AttributionBars.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { FeatureAttributionResponse } from '../../../api/contracts'
import { AttributionBars } from '../AttributionBars'

const attribution: FeatureAttributionResponse[] = [
  { feature_name: 'peer_deviation', contribution: -0.08, rationale: '' },
  { feature_name: 'anomaly_signal', contribution: 0.33, rationale: 'SHAP attribution' },
]

describe('AttributionBars', () => {
  it('sorts by |contribution| descending and signs the labels', () => {
    render(<AttributionBars attribution={attribution} />)
    const rows = screen.getAllByTestId('attribution-row')
    expect(rows[0]).toHaveTextContent('anomaly signal')
    expect(rows[0]).toHaveTextContent('+0.33')
    expect(rows[1]).toHaveTextContent('−0.08')
  })

  it('renders nothing when attribution is empty', () => {
    const { container } = render(<AttributionBars attribution={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
```

`EntityPolicyPanel.test.tsx` (mock `usePolicyItems` module):

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { PolicyItemSummaryResponse } from '../../../api/contracts'

const items: PolicyItemSummaryResponse[] = [
  {
    id: 'pi-1',
    title: 'Inpatient billing limit exceeded',
    severity: 'critical',
    status: 'open',
    target_kind: 'entity',
    target_ref: 'provider:1',
    updated_at: '2026-07-20T00:00:00Z',
  } as PolicyItemSummaryResponse,
  {
    id: 'pi-2',
    title: 'Unrelated metric item',
    severity: 'low',
    status: 'open',
    target_kind: 'metric',
    target_ref: 'weekly_carrier_billing',
    updated_at: '2026-07-20T00:00:00Z',
  } as PolicyItemSummaryResponse,
]

vi.mock('../../../api/policy', () => ({
  usePolicyItems: () => ({ data: { items }, isLoading: false, isError: false }),
}))

import { EntityPolicyPanel, policyItemsForTarget } from '../EntityPolicyPanel'
import { MemoryRouter } from 'react-router-dom'

describe('policyItemsForTarget', () => {
  it('filters by target kind and ref', () => {
    expect(policyItemsForTarget(items, 'entity', 'provider:1')).toHaveLength(1)
    expect(policyItemsForTarget(items, 'entity', 'provider:2')).toHaveLength(0)
  })
})

describe('EntityPolicyPanel', () => {
  it('renders matching items with the critical callout treatment', () => {
    render(
      <MemoryRouter>
        <EntityPolicyPanel knowledgeBaseId="kb-1" targetKind="entity" targetRef="provider:1" />
      </MemoryRouter>,
    )
    expect(screen.getByText('Inpatient billing limit exceeded')).toBeInTheDocument()
    expect(screen.getByText(/POLICY SIGNAL/)).toBeInTheDocument()
    expect(screen.queryByText('Unrelated metric item')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify failure** — both suites FAIL (modules missing).

- [ ] **Step 3: Implement `AttributionBars.tsx`:**

```tsx
import type { FeatureAttributionResponse } from '../../api/contracts'

export interface AttributionBarsProps {
  attribution: FeatureAttributionResponse[]
}

export function AttributionBars({ attribution }: AttributionBarsProps) {
  if (attribution.length === 0) {
    return null
  }
  const maxMagnitude = Math.max(...attribution.map((a) => Math.abs(a.contribution)), 0.0001)
  const sorted = [...attribution].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  )
  return (
    <div className="signal-band" data-testid="attribution-bars">
      <span className="flag-label">Feature attribution</span>
      {sorted.map((item) => {
        const raising = item.contribution >= 0
        const width = Math.round((Math.abs(item.contribution) / maxMagnitude) * 100)
        const signed = `${raising ? '+' : '−'}${Math.abs(item.contribution).toFixed(2)}`
        return (
          <div className="signal-band__row" data-testid="attribution-row" key={item.feature_name}>
            <div>
              <strong>{item.feature_name.replace(/_/g, ' ')}</strong>
              {item.rationale ? (
                <div className="metric-row__label">{item.rationale}</div>
              ) : null}
            </div>
            <div className="signal-band__bar" title={signed}>
              <div
                style={{
                  width: `${width}%`,
                  height: '100%',
                  background: raising ? 'var(--c-red)' : 'var(--c-green)',
                }}
              />
            </div>
            <span className="flag-label">{signed}</span>
          </div>
        )
      })}
    </div>
  )
}
```

(Adjust `.signal-band__row` usage: add a third `auto` column via inline `style={{ gridTemplateColumns: 'minmax(0,1fr) 120px auto' }}` on the row — keep pages.css untouched.)

- [ ] **Step 4: Implement `EntityPolicyPanel.tsx`:**

```tsx
import { Link } from 'react-router-dom'

import type { PolicyItemSummaryResponse } from '../../api/contracts'
import { usePolicyItems } from '../../api/policy'
import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'

export function policyItemsForTarget(
  items: PolicyItemSummaryResponse[],
  targetKind: 'entity' | 'alert',
  targetRef: string,
): PolicyItemSummaryResponse[] {
  return items.filter(
    (item) => item.target_kind === targetKind && item.target_ref === targetRef,
  )
}

export interface EntityPolicyPanelProps {
  knowledgeBaseId: string | null
  targetKind: 'entity' | 'alert'
  targetRef: string | null
}

export function EntityPolicyPanel({
  knowledgeBaseId,
  targetKind,
  targetRef,
}: EntityPolicyPanelProps) {
  const policyQuery = usePolicyItems(knowledgeBaseId)
  const matches = targetRef
    ? policyItemsForTarget(policyQuery.data?.items ?? [], targetKind, targetRef)
    : []
  if (matches.length === 0) {
    return (
      <EmptyState
        description="No policy items reference this record yet. Review the policy workspace for open determinations."
        title="No policy signals"
      />
    )
  }
  return (
    <div className="metric-stack" data-testid="entity-policy-panel">
      {matches.map((item) => {
        const critical = item.severity === 'critical'
        return (
          <div
            className={critical ? 'callout--warning' : undefined}
            key={item.id}
          >
            {critical ? (
              <span className="flag-label" style={{ color: 'var(--c-amber)' }}>
                ⚑ POLICY SIGNAL
              </span>
            ) : null}
            <div className="metric-row metric-row--stacked">
              <strong>{item.title}</strong>
              <div className="alert-row-card__meta">
                <Chip label={item.severity} tone={critical ? 'warning' : 'info'} />
                <Chip label={item.status} tone="info" />
              </div>
              <Link className="metric-row__label" to="/policy">
                Open in policy workspace
              </Link>
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

(Verify `PolicyItemSummaryResponse` field names against `src/api/contracts.ts` before finalizing — if `severity`/`status` enums differ, match the real names; the Chip `tone` values must be ones `Chip` accepts — check its props.)

- [ ] **Step 5: Run tests to verify pass** — both suites PASS.

- [ ] **Step 6: Commit**

```bash
git add src/components/charts/AttributionBars.tsx src/components/charts/__tests__/AttributionBars.test.tsx src/components/investigation/EntityPolicyPanel.tsx src/components/investigation/__tests__/EntityPolicyPanel.test.tsx
git commit -m "feat(ui): attribution bars + entity/alert policy panel (U2)"
```

---

### Task 5: EvidencePackViewer reshape — narrative lead + attribution section

**Files:**
- Modify: `chili_app/src/components/investigation/EvidencePackViewer.tsx` (section order at ~53-104)
- Test: modify `chili_app/src/components/investigation/__tests__/EvidencePackViewer.test.tsx` (append; existing tests must keep passing unless they pin the old section ORDER — reordering assertions may be updated, content assertions may not be weakened)

**Interfaces:**
- Consumes: `AttributionBars` (Task 4), `.callout--ai`, `.flag-label` (Task 1); `pack.attribution?`, `pack.narrative_sections?` (optional generated fields).
- Produces: unchanged `EvidencePackViewerProps` — Tasks 7, 8 keep consuming it as today.

- [ ] **Step 1: Write the failing tests** (append to the existing test file, reusing its existing pack fixture builder — read the file first and extend the fixture with `attribution` and `narrative_sections`):

```tsx
it('leads with the AI narrative band and renders narrative sections', () => {
  renderViewer({
    ...basePack,
    reasoning: 'The provider shows synchronized anomalies.',
    narrative_sections: [
      { heading: 'Risk Factor', body: 'Self-history anomaly z=4.5.', evidence_refs: ['e-1'] },
    ],
  })
  const narrative = screen.getByTestId('evidence-narrative')
  expect(narrative).toHaveTextContent('AI NARRATIVE')
  expect(narrative).toHaveTextContent('The provider shows synchronized anomalies.')
  expect(screen.getByText('Risk Factor')).toBeInTheDocument()
  expect(screen.getByText('Self-history anomaly z=4.5.')).toBeInTheDocument()
})

it('renders attribution bars when the pack carries attribution', () => {
  renderViewer({
    ...basePack,
    attribution: [{ feature_name: 'anomaly_signal', contribution: 0.33, rationale: '' }],
  })
  expect(screen.getByTestId('attribution-bars')).toBeInTheDocument()
})

it('omits the attribution section for packs without the field', () => {
  renderViewer(basePack)
  expect(screen.queryByTestId('attribution-bars')).not.toBeInTheDocument()
})
```

(`renderViewer`/`basePack`: adapt to the file's existing helpers — if none exist, add a local helper that renders with `subgraph={{nodes:[],edges:[]}}`, `entityTypes={[]}`.)

- [ ] **Step 2: Run to verify failure** — the three new tests FAIL (no `evidence-narrative` testid, no attribution rendering).

- [ ] **Step 3: Implement.** In `EvidencePackViewer.tsx`, replace the current heading + reasoning block (~:56-57) with the narrative lead band, and insert the attribution section after the confidence/score chips:

```tsx
<div className="callout--ai" data-testid="evidence-narrative">
  <span className="flag-label" style={{ color: 'var(--c-cyan)' }}>
    ◆ AI NARRATIVE
  </span>
  <p className="page-copy-block" style={{ fontSize: '14px' }}>
    {pack.reasoning}
  </p>
  {(pack.narrative_sections ?? []).map((section) => (
    <div className="metric-row metric-row--stacked" key={section.heading + section.body}>
      <strong>{section.heading}</strong>
      <span className="metric-row__label">{section.body}</span>
    </div>
  ))}
</div>
```

and after the score chips:

```tsx
{pack.attribution && pack.attribution.length > 0 ? (
  <AttributionBars attribution={pack.attribution} />
) : null}
```

Keep the "Evidence pack" strong tag as the card's title if existing tests assert it; the remaining sections (subgraph, contributing items, citations) stay in order.

- [ ] **Step 4: Run the full viewer suite** — `npm run test:run -- src/components/investigation/__tests__/EvidencePackViewer.test.tsx` → PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/components/investigation/EvidencePackViewer.tsx src/components/investigation/__tests__/EvidencePackViewer.test.tsx
git commit -m "feat(ui): evidence viewer leads with AI narrative + SHAP attribution bars (U2)"
```

---

### Task 6: GraphCanvas cluster overlay + dormant predicted links + ClusterMembershipPanel

**Files:**
- Modify: `chili_app/src/components/investigation/GraphCanvas.tsx`
- Create: `chili_app/src/components/investigation/ClusterMembershipPanel.tsx`
- Test: modify `chili_app/src/components/investigation/__tests__/GraphCanvas.test.tsx` (append), create `chili_app/src/components/investigation/__tests__/ClusterMembershipPanel.test.tsx`

**Interfaces:**
- Consumes: `clusterColorFor`, `PREDICTED_LINK_COLOR`, `PREDICTED_LINK_DASH`, `isPredictedRelationship`, `predictedConfidenceFor`, `communityIdFor` (Task 1 + existing); `ClusterResult {cluster_id, anomaly_score, entity_ids?, label?}`.
- Produces:
  - `GraphCanvasProps` gains OPTIONAL `clusterMode?: boolean` (default false) and `highlightedEntityIds?: readonly string[]` (membership-panel hover/select highlight; highlighted nodes render with a `#fbbf24` ring exactly like selection). When `clusterMode` is true and an entity has a `communityIdFor` value, node color = `clusterColorFor(communityId)`; else the existing type color. Legend switches to cluster swatches in cluster mode (never both legends at once — design risk mitigation).
  - Link styling: `linkColor` returns `PREDICTED_LINK_COLOR` for predicted relationships (else the existing rgba), `linkLineDash` returns `[...PREDICTED_LINK_DASH]` for predicted else `null`, link tooltip (`linkLabel`) shows `predicted · {confidence}` when `predictedConfidenceFor` is non-null. The relationship objects must be threaded into the link data build so the callbacks can check them (extend the existing `graphData` memo: each link keeps a `predicted: boolean` and `confidence: number | null`).
  - `ClusterMembershipPanel` props: `{ clusters: ClusterResult[]; selectedClusterId: string | null; onSelectCluster: (clusterId: string | null) => void }` — Task 7 consumes; rows show `cluster-swatch` (same `clusterColorFor`), `label ?? cluster_id`, member count, anomaly chip (`{Math.round(anomaly_score*100)} anomaly`, tone warning); clicking a row toggles selection (calls back with null when re-clicking the selected one). Ordering: anomaly_score desc, then member count desc (centrality ordering is phase 2 — spec §6).

- [ ] **Step 1: Write the failing tests.** Append to `GraphCanvas.test.tsx` (mirror the file's existing mock approach for react-force-graph-2d — read it first; assert via the exported pure helpers if the mock doesn't expose callbacks):

```tsx
it('colors nodes by community in cluster mode and by type otherwise', () => {
  // Use the same harness the file already uses to inspect graphData/nodeColor;
  // entity fixture carries properties.community_id = 'community-3'.
  // cluster mode ON  -> expect clusterColorFor('community-3')
  // cluster mode OFF -> expect colorForEntityType(entity.type, entityTypes)
})

it('marks predicted links dashed with confidence in the tooltip', () => {
  // relationship fixture with metadata { predicted: true, confidence: 0.7 }
  // expect link.predicted === true, dash [4,3], label containing '0.7'
})
```

Write these against the file's ACTUAL test harness (it exists — extend, don't rewrite). `ClusterMembershipPanel.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ClusterResult } from '../../../api/contracts'
import { ClusterMembershipPanel } from '../ClusterMembershipPanel'

const clusters: ClusterResult[] = [
  { cluster_id: 'c-low', anomaly_score: 0.1, entity_ids: ['a'], label: null },
  { cluster_id: 'c-high', anomaly_score: 0.9, entity_ids: ['b', 'c'], label: 'dense referrals' },
]

describe('ClusterMembershipPanel', () => {
  it('orders by anomaly score desc and shows label, count, anomaly chip', () => {
    render(
      <ClusterMembershipPanel clusters={clusters} onSelectCluster={vi.fn()} selectedClusterId={null} />,
    )
    const rows = screen.getAllByTestId('cluster-row')
    expect(rows[0]).toHaveTextContent('dense referrals')
    expect(rows[0]).toHaveTextContent('2 members')
    expect(rows[0]).toHaveTextContent('90 anomaly')
  })

  it('toggles selection through onSelectCluster', () => {
    const onSelect = vi.fn()
    render(
      <ClusterMembershipPanel clusters={clusters} onSelectCluster={onSelect} selectedClusterId="c-high" />,
    )
    fireEvent.click(screen.getAllByTestId('cluster-row')[0])
    expect(onSelect).toHaveBeenCalledWith(null)
  })
})
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement GraphCanvas changes** (extend the `graphData` memo: nodes gain `communityColor: communityIdFor(entity) ? clusterColorFor(communityIdFor(entity)!) : null`; links gain `predicted`/`confidence` from the helpers; `nodeColor` prefers `clusterMode && node.communityColor ? node.communityColor : node.color` with the selection/highlight override first; add `linkLineDash={(link) => (link.predicted ? [...PREDICTED_LINK_DASH] : null)}`, `linkLabel` for predicted confidence; legend block renders cluster swatches from the distinct communityColors when `clusterMode`). Implement `ClusterMembershipPanel.tsx`:

```tsx
import type { ClusterResult } from '../../api/contracts'
import { clusterColorFor } from '../../utils/graphStyles'
import { Chip } from '../ui/Chip'

export interface ClusterMembershipPanelProps {
  clusters: ClusterResult[]
  selectedClusterId: string | null
  onSelectCluster: (clusterId: string | null) => void
}

export function ClusterMembershipPanel({
  clusters,
  selectedClusterId,
  onSelectCluster,
}: ClusterMembershipPanelProps) {
  const ordered = [...clusters].sort(
    (a, b) =>
      b.anomaly_score - a.anomaly_score ||
      (b.entity_ids?.length ?? 0) - (a.entity_ids?.length ?? 0),
  )
  return (
    <div className="metric-stack" data-testid="cluster-membership-panel">
      <span className="flag-label">Clusters</span>
      {ordered.map((cluster) => {
        const selected = cluster.cluster_id === selectedClusterId
        return (
          <button
            className="metric-row"
            data-testid="cluster-row"
            key={cluster.cluster_id}
            onClick={() => onSelectCluster(selected ? null : cluster.cluster_id)}
            style={selected ? { outline: '1px solid var(--c-cyan)' } : undefined}
            type="button"
          >
            <span
              className="cluster-swatch"
              style={{ background: clusterColorFor(cluster.cluster_id) }}
            />
            <strong>{cluster.label ?? cluster.cluster_id}</strong>
            <span className="metric-row__label">
              {cluster.entity_ids?.length ?? 0} members
            </span>
            <Chip label={`${Math.round(cluster.anomaly_score * 100)} anomaly`} tone="warning" />
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Run both suites + full Vitest** — existing GraphCanvas tests are the no-regression gate (plain mode must render exactly as before when `clusterMode` is absent).

- [ ] **Step 5: Commit**

```bash
git add src/components/investigation/GraphCanvas.tsx src/components/investigation/ClusterMembershipPanel.tsx src/components/investigation/__tests__/
git commit -m "feat(ui): cluster overlay + membership panel + dormant predicted links (U2)"
```

---

### Task 7: InvestigationWorkbenchPage restructure + orphan deletion (D1)

**Files:**
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx` (full restructure per design §4.1)
- Delete: `chili_app/src/components/investigation/EntityDetailPanel.tsx`, `EntityDetailPanel.module.css`, `EvidencePanel.tsx`, `EvidencePanel.module.css`, `TimelinePanel.tsx`, and their `__tests__` files
- Test: modify `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`

**Interfaces:**
- Consumes: everything produced by Tasks 1-6. Capability gates from `useDomainFeatures().data?.capabilities`.
- Produces: page structure — search rail (`.workbench-rail`: KB select + entity search + results, moved unchanged) + dossier column: `EntityDossierHeader` → `SignalBand` (factors from `useRiskScore`, hidden when risk unavailable) → capability-gated `Tabs` (`idPrefix="workbench-tab"`, `ariaControlsPrefix="workbench-tabpanel"`) with panels:
  - `signals` (always when `risk_scoring` or `timeseries`): `AnomalyTrendPanel` (absent when `timeseries` false) + full factor detail list (today's risk-factor card content grouped by family — keep the existing JSX from :245-261 as the detail list).
  - `network` (always): depth select + `GraphCanvas` (`clusterMode={gnn && clusters.length > 0}`, `highlightedEntityIds` from the selected cluster's `entity_ids`) + `ClusterMembershipPanel` (only when `gnn` and clusters exist).
  - `policy` (`explainability` only): `EntityPolicyPanel targetKind="entity" targetRef={selectedEntityId}`.
  - `evidence` (`explainability` only): the existing evidence-pack block moved into the panel; EmptyState pointing at the Alert Feed when no alert/pack.
  - Tab panels get `className="fade-up"` keyed by active tab. If only one tab survives gating, render its panel without the strip.

- [ ] **Step 1: Update the page tests FIRST** (they define the target): rewrite `InvestigationWorkbenchPage.test.tsx` assertions that pin the old vertical-stack structure into the new shape — tab strip present with capability-complete config, absent tabs under a capabilities fixture with `explainability: false`, signal band renders factor names, dossier renders title via display_fields. Keep every existing DATA assertion (entity titles, availability reasons, search flow) — they must survive the restructure. Run: FAIL.

- [ ] **Step 2: Restructure the page.** Preserve ALL existing hooks/data wiring (`useRiskScore`, `useEntityTimeseries`, alerts/evidence queries, `useInvestigationNeighborhood`, search + URL param handling) — this is a layout/composition change. Add `useGnnClusters(activeKnowledgeBaseId)` and local `selectedClusterId` state. Tab list built from capabilities:

```tsx
const capabilities = featuresQuery.data?.capabilities
const tabs = [
  { id: 'signals', label: 'Signals' },
  { id: 'network', label: 'Network' },
  ...(capabilities?.explainability ? [{ id: 'policy', label: 'Policy' }, { id: 'evidence', label: 'Evidence' }] : []),
]
```

- [ ] **Step 3: Delete the three orphan components + CSS modules + tests.** Run a repo grep for each name first (`EntityDetailPanel|EvidencePanel|TimelinePanel`) to confirm no live imports outside their own tests; `communityIdFor` keeps its Task 6 consumer.

- [ ] **Step 4: Run the page suite + full Vitest + build** — `npm run test:run` and `npm run build`. Expected: green, no unused-import fallout from deletions.

- [ ] **Step 5: Commit**

```bash
git add -A src/pages/InvestigationWorkbenchPage.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/components/investigation
git commit -m "feat(ui): workbench dossier layout with capability-gated tabs; retire orphan panels (U2)"
```

---

### Task 8: Alert Feed triage rows + real evidence subgraph + policy chips

**Files:**
- Modify: `chili_app/src/pages/AlertFeedPage.tsx`
- Test: modify `chili_app/src/pages/__tests__/AlertFeedPage.test.tsx` (append/adjust)

**Interfaces:**
- Consumes: `.triage-row*`, `.flag-label` (Task 1); `policyItemsForTarget` (Task 4); `useInvestigationNeighborhood` + `useDomainConfig` (existing hooks); reshaped `EvidencePackViewer` (Task 5).
- Produces: exported pure helper `flagLabelFor(alert: { tags: string[]; severity: string }): string` — tags uppercased and joined with ' · '; fallback = severity uppercased (never an invented domain string). Task 9 reuses it for the dashboard lead card.

- [ ] **Step 1: Write the failing tests** (append):

```tsx
import { flagLabelFor } from '../AlertFeedPage'

describe('flagLabelFor', () => {
  it('joins tags uppercase with middle dots', () => {
    expect(flagLabelFor({ tags: ['upcoding', 'hcpcs-consolidation'], severity: 'high' })).toBe(
      'UPCODING · HCPCS-CONSOLIDATION',
    )
  })
  it('falls back to the severity word when no tags', () => {
    expect(flagLabelFor({ tags: [], severity: 'critical' })).toBe('CRITICAL')
  })
})
```

Plus a render assertion in the page suite: the first alert card shows `data-testid="triage-numeral"` containing `Math.round(confidence*100)` and a `.flag-label` with the joined tags.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement.**
  - Export `flagLabelFor` from the page module (above the component):

```tsx
export function flagLabelFor(alert: { tags: string[]; severity: string }): string {
  if (alert.tags.length > 0) {
    return alert.tags.map((tag) => tag.replace(/-/g, ' ').toUpperCase().replace(/ /g, '-')).join(' · ')
  }
  return alert.severity.toUpperCase()
}
```

  (Simplify: `alert.tags.map((t) => t.toUpperCase()).join(' · ')` if the mockup treatment reads better with raw slugs — pick ONE and make the test agree.)
  - Restyle the row (:99-190): wrap in `.triage-row`; numeral block `<div className="triage-row__numeral" data-testid="triage-numeral" style={{color: severity-stepped}}>{Math.round(alert.confidence * 100)}</div>` (color: critical/high `var(--c-red)`, medium `var(--c-amber)`, else `var(--c-green)`); `RiskBadge` in the header actions is REPLACED by the numeral (no duplicate number); insert `<span className="flag-label">{flagLabelFor(alert)}</span>` between title and reasoning; reasoning clamps to one line (`style={{overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}` or an existing utility class).
  - Evidence expansion (:199-204): for the selected alert, call `const neighborhoodQuery = useInvestigationNeighborhood(selectedAlert?.knowledge_base_id ?? null, selectedAlert?.entity_id ?? null, 1)` at the top level of the component (hooks can't be conditional — key off `selectedAlert`), and pass `subgraph={toSubgraphResult(neighborhoodQuery.data) ?? { nodes: [], edges: [] }}` and `entityTypes={domainConfig ? domainConfig.entities.map((e) => e.name) : []}` (reuse the exact `toSubgraphResult` helper the workbench page uses — import it from where it lives or lift it into `src/utils/` if it's page-local; lifting is preferred, one shared implementation).
  - Policy chip: `usePolicyItems(activeKb)` once per page; per row, `policyItemsForTarget(items, 'alert', alert.id).length + policyItemsForTarget(items, 'entity', alert.entity_id).length > 0` → `<Chip label="policy" tone="warning" />` in the meta row. Both the chip and the whole Evidence action are rendered only when `capabilities.explainability`.

- [ ] **Step 4: Run the page suite + full Vitest** — existing action-flow tests (Investigate/Ask AI/Promote/Ack) must keep passing untouched.

- [ ] **Step 5: Commit**

```bash
git add src/pages/AlertFeedPage.tsx src/pages/__tests__/AlertFeedPage.test.tsx
git commit -m "feat(ui): risk-ranked triage rows, live evidence subgraph, policy chips (U2)"
```

---

### Task 9: Dashboard pass — copy, lead-card flag treatment, cluster swatches + links

**Files:**
- Modify: `chili_app/src/pages/DashboardPage.tsx`
- Test: modify `chili_app/src/pages/__tests__/DashboardPage.test.tsx`

**Interfaces:**
- Consumes: `flagLabelFor` (Task 8), `clusterColorFor`, `.cluster-swatch`, `.triage-row*`, `.flag-label` (Task 1); `useDomainConfig` for the display name.

- [ ] **Step 1: Write the failing tests** (append): (a) header no longer contains "Phase 5 data live" and instead shows the domain `display_name` chip; (b) the lead alert card contains a `.flag-label` with the tags treatment and a triage numeral; (c) cluster rows render a `data-testid="cluster-swatch"` whose inline background equals `clusterColorFor(cluster.cluster_id)` and an "Open in workbench" link with `href` containing `/investigation/` + the first entity id + `?kb=`; (d) with `gnn: false` capabilities fixture, the Graph clusters panel is ABSENT entirely (not an EmptyState).

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement.**
  - :148 — `<Chip label={domainConfig?.display_name ?? 'Live'} tone="info" />` (drop the stale copy; also update the stale `subtitle` at :150 to a neutral one-liner: `"Live operational overview for the active knowledge base."`).
  - Lead alert card (:202-218): add the `.triage-row` treatment — numeral `Math.round(leadAlert.confidence * 100)` + `flagLabelFor(leadAlert)` above the reasoning; wrap with a `Link` to `/investigation/${leadAlert.entity_id}?kb=${leadAlert.knowledge_base_id}` on an "Investigate" action (match the AlertFeed Investigate link idiom).
  - Clusters panel (:303-320): prepend `<span className="cluster-swatch" data-testid="cluster-swatch" style={{ background: clusterColorFor(cluster.cluster_id) }} />` to each row; add an "Open in workbench" `Link` per row targeting `/investigation/${cluster.entity_ids?.[0] ?? ''}?kb=${activeKb}` (row link only when a member exists; the design's "highest-anomaly member" refinement is phase 2 — the ids list carries no per-member scores). Wrap the whole panel in `capabilities?.gnn ? (...) : null` — EmptyState remains only for `gnn` true + zero clusters.

- [ ] **Step 4: Run the dashboard suite + full Vitest.**

- [ ] **Step 5: Commit**

```bash
git add src/pages/DashboardPage.tsx src/pages/__tests__/DashboardPage.test.tsx
git commit -m "feat(ui): dashboard copy, lead-card triage treatment, live cluster panel (U2)"
```

---

### Task 10: Unit-gate closeout + docs/backlog reconciliation

**Files:**
- Modify: `chili_app/README.md` (component inventory / page descriptions if they enumerate the touched pages)
- Modify: `docs/backlog/frontend.md` (per design §6: phase-2 records — Timeline tab needs a detection-events API; peer-comparison bars need a peer-distribution endpoint; cluster centrality ordering; predicted-link TRANSPORT backend dependency (coordinator never persists `GnnAnalysisResponse.predicted_links` — record as the backend story the dormant canvas support waits on); BL-050 story statuses per file conventions)
- Modify: `docs/backlog/README.md` (regenerated rollup if statuses change), `docs/project/planning/backlog.md` BL-050 row, `docs/project/planning/sprints/2026-28.md` (U2 progress entry — code-complete, browser/e2e verification pending Task 11; do NOT claim live-verified)
- Modify: `docs/wiki/` pages describing the three pages/components if their file inventories or behavior claims are staled (grep for EntityDetailPanel/EvidencePanel/TimelinePanel — the deletions must be reflected; check `docs/wiki/modules/` frontend page if one exists)

**Steps:**

- [ ] **Step 1:** Run the full unit gates from `chili_app/`: `npm run test:run`, `npm run lint`, `npm run build`. All green — fix anything red before docs.
- [ ] **Step 2:** Make the doc edits above; from repo root run `backend/.venv/bin/python scripts/backlog_consistency.py --check` (regenerate rollups via the tool if statuses changed; never hand-edit generated sections).
- [ ] **Step 3:** Commit:

```bash
git add chili_app/README.md docs/
git commit -m "docs(frontend,backlog,wiki): U2 reshape reconciliation + phase-2 fences (U2)"
```

---

### Task 11: Live verification — RESERVED FOR THE CONTROLLER

Against the full stack (`make dev`, CMS DE-SynPUF pack, TN demo KB with B2/B3 data):

- [ ] Workbench `/investigation/<provider-with-signals>?kb=<kb>`: dossier header (Oxanium numeral, severity color), AI signal band with both factor families, tabs Signals/Network/Policy/Evidence all present; Signals tab shows the anomaly chart with red markers; Network tab shows cluster-colored nodes + membership panel (B1 clusters exist), selecting a cluster highlights members; Evidence tab shows the narrative-lead viewer with SHAP bars (B3 packs exist on the TN KB).
- [ ] Alert Feed: triage numerals + flag labels; expanding evidence renders a REAL subgraph (not the empty state) with correctly colored nodes; policy chips only where items reference the alert/entity.
- [ ] Dashboard: display-name chip (no "Phase 5" copy), lead card flag treatment, clusters panel with swatches matching the workbench overlay colors, workbench links navigate correctly.
- [ ] Capability degradation: switch to the housing pack via `POST /config/switch` — its four routed pages render untouched; then simulate capability-off states (housing pack has `gnn:false`, `peer_stats:false` — verify the reshaped pages under a pack state where they are routed): no CMS strings anywhere, no crashed gates, absent-not-broken surfaces per the design §5 matrix. Switch back to `medicare_fraud_cms_desynpuf` afterwards (NOT the generic `medicare_fraud` pack — it has no storage pins and orphans the KB registry view).
- [ ] Playwright e2e: update/extend `chili_app/e2e/investigation-workbench.spec.ts`, `alert-feed-evidence.spec.ts`, and `smoke.spec.ts` for the reshaped structure (tab navigation, dossier presence, triage rows, narrative band); run the full e2e suite against the running stack. No `page.route` mocks of the subjects under test.
- [ ] Zero browser console errors on all three pages; screenshots into the session scratchpad.
- [ ] Full gates: `npm run test:run`, `npm run lint`, `npm run build`, backend `make test` (unchanged backend — regression only), `backlog_consistency.py --check`.

---

## Self-review notes (applied)

- Spec coverage: §4.1 workbench (T2/T3/T6/T7), §4.2 dashboard (T9), §4.3 alert feed (T8), D1 deletions (T7), D4 overlay/membership/predicted (T1/T6), D5 viewer (T4/T5), D6 triage+subgraph (T8), D7 policy (T4/T7/T8), D9 motion (T1/T7), §5 degradation matrix (gates in T7/T8/T9, verified T11), §6 phase-2 fences + §7 contract rows (T10 records; attribution/narrative CONSUMED live since B3 landed them — supersedes the spec's "hidden until B3" row; predicted links dormant per verified transport absence).
- Type consistency: `clusterColorFor`/`flagLabelFor`/`policyItemsForTarget`/`AttributionBars`/`ClusterMembershipPanel` names and prop shapes identical at production and consumption sites; `Tabs`/`ConfidenceBar`/`RiskBadge` props match the verified fact sheet.
- Known simplifications: dashboard cluster "open in workbench" targets the first member (per-member scores unavailable — phase 2); AttributionBars third column via inline grid override rather than a new CSS class; predicted-link tests exercise the dormant path with synthetic metadata (no live data exists — by design).
