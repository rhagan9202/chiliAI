import { describe, expect, it } from 'vitest'

import {
  applyCaseFilters,
  EMPTY_CASE_FILTERS,
  parseCaseFilters,
  serializeCaseFilters,
  summarizeCaseFilters,
} from '../caseFilters'

const CASES = [
  { id: 'c1', title: 'Redwood DME escalation', status: 'open', priority: 'high' },
  { id: 'c2', title: 'North Harbor review', status: 'in_review', priority: 'medium' },
  { id: 'c3', title: 'Cedar Ridge closure', status: 'closed', priority: 'low' },
]

const ids = (items: readonly { id: string }[]) => items.map((item) => item.id)

describe('applyCaseFilters', () => {
  it('returns everything when nothing is selected', () => {
    expect(ids(applyCaseFilters(CASES, EMPTY_CASE_FILTERS))).toEqual(['c1', 'c2', 'c3'])
  })

  it('treats multiple statuses as OR, which the single-select row could not', () => {
    const filtered = applyCaseFilters(CASES, {
      ...EMPTY_CASE_FILTERS,
      statuses: ['open', 'in_review'],
    })

    expect(ids(filtered)).toEqual(['c1', 'c2'])
  })

  it('searches the case title', () => {
    expect(ids(applyCaseFilters(CASES, { ...EMPTY_CASE_FILTERS, search: 'harbor' }))).toEqual(['c2'])
  })

  it('combines status and search', () => {
    const filtered = applyCaseFilters(CASES, {
      ...EMPTY_CASE_FILTERS,
      statuses: ['closed'],
      search: 'cedar',
    })

    expect(ids(filtered)).toEqual(['c3'])
  })
})

describe('URL round-trip', () => {
  it('survives a reload', () => {
    const state = { statuses: ['open', 'closed'], search: 'redwood' }

    expect(parseCaseFilters(new URLSearchParams(serializeCaseFilters(state)))).toEqual(state)
  })

  it('writes nothing when unfiltered', () => {
    expect(serializeCaseFilters(EMPTY_CASE_FILTERS).toString()).toBe('')
  })

  it('ignores parameters it does not own, so ?kb= and ?case= survive', () => {
    const params = new URLSearchParams('kb=kb-1&case=c1&status=open')

    expect(parseCaseFilters(params)).toEqual({ ...EMPTY_CASE_FILTERS, statuses: ['open'] })
  })
})

describe('summarizeCaseFilters', () => {
  it('states what is shown when unfiltered', () => {
    expect(summarizeCaseFilters({ shown: 3, total: 3, filters: EMPTY_CASE_FILTERS })).toBe(
      'Showing all 3 cases',
    )
  })

  it('states how much is hidden when filtered', () => {
    expect(
      summarizeCaseFilters({ shown: 1, total: 3, filters: { ...EMPTY_CASE_FILTERS, statuses: ['open'] } }),
    ).toBe('Showing 1 of 3 cases')
  })
})
