import { describe, expect, it } from 'vitest'

import {
  EMPTY_POLICY_FILTERS,
  hasActivePolicyFilters,
  parsePolicyFilters,
  serializePolicyFilters,
  summarizePolicyFilters,
  togglePolicyStatus,
  totalFromStatusCounts,
} from '../policyFilters'

describe('policyFilters', () => {
  it('round-trips through the URL', () => {
    const filters = { statuses: ['open', 'escalated'], search: 'upcoding' }

    const parsed = parsePolicyFilters(serializePolicyFilters(filters))

    expect(parsed).toEqual(filters)
  })

  it('reads only the parameters it owns, so ?kb= and ?item= survive', () => {
    const params = new URLSearchParams('kb=kb-1&item=item-9&status=open&q=fraud')

    expect(parsePolicyFilters(params)).toEqual({ statuses: ['open'], search: 'fraud' })
    expect(serializePolicyFilters({ statuses: ['open'], search: 'fraud' }).toString()).toBe(
      'status=open&q=fraud',
    )
  })

  it('omits an empty search from the URL rather than writing q=', () => {
    expect(serializePolicyFilters({ statuses: ['open'], search: '' }).toString()).toBe(
      'status=open',
    )
  })

  it('toggles a status on and back off', () => {
    const once = togglePolicyStatus(EMPTY_POLICY_FILTERS, 'open')
    expect(once.statuses).toEqual(['open'])

    const twice = togglePolicyStatus(once, 'escalated')
    expect(twice.statuses).toEqual(['open', 'escalated'])

    expect(togglePolicyStatus(twice, 'open').statuses).toEqual(['escalated'])
  })

  it('knows when a filter is actually active', () => {
    expect(hasActivePolicyFilters(EMPTY_POLICY_FILTERS)).toBe(false)
    expect(hasActivePolicyFilters({ statuses: ['open'], search: '' })).toBe(true)
    expect(hasActivePolicyFilters({ statuses: [], search: 'a' })).toBe(true)
  })

  it('totals the knowledge base from the status counts', () => {
    expect(totalFromStatusCounts({ open: 2, escalated: 3, rejected: 1 })).toBe(6)
    expect(totalFromStatusCounts({})).toBe(0)
  })

  it('distinguishes a filtered result line from an unfiltered one', () => {
    expect(
      summarizePolicyFilters({ shown: 2, total: 9, filters: { statuses: ['open'], search: '' } }),
    ).toBe('Showing 2 of 9 items')
    expect(
      summarizePolicyFilters({ shown: 9, total: 9, filters: EMPTY_POLICY_FILTERS }),
    ).toBe('Showing all 9 items')
    // countLabel singularises, so a one-item queue does not read "1 items".
    expect(
      summarizePolicyFilters({ shown: 1, total: 1, filters: EMPTY_POLICY_FILTERS }),
    ).toBe('Showing all 1 item')
  })
})
