import { describe, expect, it } from 'vitest'

import type { AlertListItem } from '../../api/contracts'
import {
  applyAlertFilters,
  ALERT_SORTS,
  countBy,
  EMPTY_ALERT_FILTERS,
  parseAlertFilters,
  serializeAlertFilters,
  summarizeAlertFilters,
} from '../alertFilters'

function alert(overrides: Partial<AlertListItem> & Pick<AlertListItem, 'id'>): AlertListItem {
  return {
    knowledge_base_id: 'kb-1',
    entity_id: 'provider-1',
    entity_type: 'provider',
    entity_label: 'Redwood DME Group',
    severity: 'high',
    status: 'open',
    title: 'Outlier billing concentration',
    reasoning: '',
    confidence: 0.5,
    evidence_pack_id: null,
    created_at: '2026-07-20T00:00:00Z',
    tags: [],
    ...overrides,
  } as AlertListItem
}

const ALERTS = [
  alert({ id: 'a1', severity: 'critical', status: 'open', confidence: 0.9, created_at: '2026-07-26T00:00:00Z' }),
  alert({ id: 'a2', severity: 'critical', status: 'acknowledged', confidence: 0.8, created_at: '2026-07-25T00:00:00Z' }),
  alert({ id: 'a3', severity: 'medium', status: 'open', confidence: 0.7, created_at: '2026-07-24T00:00:00Z', entity_label: 'North Harbor Imaging' }),
  alert({ id: 'a4', severity: 'low', status: 'resolved', confidence: 0.2, created_at: '2026-07-01T00:00:00Z', title: 'Referral concentration anomaly' }),
]

const ids = (items: readonly { id: string }[]) => items.map((item) => item.id)

describe('applyAlertFilters', () => {
  it('returns everything when nothing is selected', () => {
    expect(ids(applyAlertFilters(ALERTS, EMPTY_ALERT_FILTERS))).toEqual(['a1', 'a2', 'a3', 'a4'])
  })

  it('expresses critical AND unacknowledged in one view', () => {
    // The single-select chip row could not say this — the product's most
    // common triage filter (UXA-401).
    const filtered = applyAlertFilters(ALERTS, {
      ...EMPTY_ALERT_FILTERS,
      severities: ['critical'],
      statuses: ['open'],
    })

    expect(ids(filtered)).toEqual(['a1'])
  })

  it('treats multiple selections within a dimension as OR', () => {
    const filtered = applyAlertFilters(ALERTS, {
      ...EMPTY_ALERT_FILTERS,
      severities: ['critical', 'medium'],
    })

    expect(ids(filtered)).toEqual(['a1', 'a2', 'a3'])
  })

  it('searches the entity label', () => {
    const filtered = applyAlertFilters(ALERTS, { ...EMPTY_ALERT_FILTERS, search: 'harbor' })

    expect(ids(filtered)).toEqual(['a3'])
  })

  it('searches the alert title', () => {
    const filtered = applyAlertFilters(ALERTS, { ...EMPTY_ALERT_FILTERS, search: 'referral' })

    expect(ids(filtered)).toEqual(['a4'])
  })

  it('filters by date range inclusively', () => {
    const filtered = applyAlertFilters(ALERTS, {
      ...EMPTY_ALERT_FILTERS,
      from: '2026-07-24',
      to: '2026-07-25',
    })

    expect(ids(filtered)).toEqual(['a2', 'a3'])
  })

  it('sorts newest first by default', () => {
    expect(ids(applyAlertFilters(ALERTS, EMPTY_ALERT_FILTERS))).toEqual(['a1', 'a2', 'a3', 'a4'])
  })

  it('sorts by severity, breaking ties on recency', () => {
    const filtered = applyAlertFilters(ALERTS, { ...EMPTY_ALERT_FILTERS, sort: 'severity' })

    expect(ids(filtered)).toEqual(['a1', 'a2', 'a3', 'a4'])
  })

  it('sorts by confidence', () => {
    const filtered = applyAlertFilters(ALERTS, { ...EMPTY_ALERT_FILTERS, sort: 'confidence' })

    expect(ids(filtered)).toEqual(['a1', 'a2', 'a3', 'a4'])
  })

  it('sorts oldest first when asked', () => {
    const filtered = applyAlertFilters(ALERTS, { ...EMPTY_ALERT_FILTERS, sort: 'oldest' })

    expect(ids(filtered)).toEqual(['a4', 'a3', 'a2', 'a1'])
  })

  it('offers exactly the documented sorts', () => {
    expect(ALERT_SORTS.map((option) => option.id)).toEqual([
      'newest',
      'oldest',
      'severity',
      'confidence',
    ])
  })
})

describe('countBy', () => {
  it('counts each option so a filter can show what it would return', () => {
    expect(countBy(ALERTS, (item) => item.severity)).toEqual({
      critical: 2,
      medium: 1,
      low: 1,
    })
  })
})

describe('URL round-trip', () => {
  it('survives a reload with every dimension set', () => {
    const state = {
      severities: ['critical', 'high'],
      statuses: ['open'],
      search: 'redwood',
      sort: 'severity' as const,
      from: '2026-07-01',
      to: '2026-07-27',
    }

    const restored = parseAlertFilters(new URLSearchParams(serializeAlertFilters(state)))

    expect(restored).toEqual(state)
  })

  it('writes nothing for an empty filter so the URL stays clean', () => {
    expect(serializeAlertFilters(EMPTY_ALERT_FILTERS).toString()).toBe('')
  })

  it('ignores parameters it does not own, so ?kb= survives', () => {
    const params = new URLSearchParams('kb=kb-1&severity=critical')

    expect(parseAlertFilters(params)).toEqual({
      ...EMPTY_ALERT_FILTERS,
      severities: ['critical'],
    })
  })

  it('falls back to the default sort when the URL names an unknown one', () => {
    expect(parseAlertFilters(new URLSearchParams('sort=nonsense')).sort).toBe('newest')
  })
})

describe('summarizeAlertFilters', () => {
  it('states what is being shown when nothing is filtered', () => {
    expect(summarizeAlertFilters({ shown: 4, total: 4, filters: EMPTY_ALERT_FILTERS })).toBe(
      'Showing all 4 alerts',
    )
  })

  it('states how much of the queue is in view when filtered', () => {
    expect(
      summarizeAlertFilters({
        shown: 1,
        total: 4,
        filters: { ...EMPTY_ALERT_FILTERS, severities: ['critical'] },
      }),
    ).toBe('Showing 1 of 4 alerts')
  })

  it('agrees in number for a single result', () => {
    expect(summarizeAlertFilters({ shown: 1, total: 1, filters: EMPTY_ALERT_FILTERS })).toBe(
      'Showing all 1 alert',
    )
  })
})
