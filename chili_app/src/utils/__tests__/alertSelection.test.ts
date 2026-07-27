import { describe, expect, it } from 'vitest'

import {
  clearSelection,
  describeSelection,
  pruneSelection,
  selectAll,
  toggleSelection,
} from '../alertSelection'

describe('toggleSelection', () => {
  it('adds an unselected alert', () => {
    expect([...toggleSelection(new Set(['a1']), 'a2')]).toEqual(['a1', 'a2'])
  })

  it('removes an already selected alert', () => {
    expect([...toggleSelection(new Set(['a1', 'a2']), 'a1')]).toEqual(['a2'])
  })

  it('does not mutate the selection it was given', () => {
    const current = new Set(['a1'])

    toggleSelection(current, 'a2')

    expect([...current]).toEqual(['a1'])
  })
})

describe('selectAll', () => {
  it('selects exactly what is on screen, not the whole queue', () => {
    // "Select all" means all *in the current filter* — acting on rows the
    // analyst cannot see would be a trap (UXA-406).
    expect([...selectAll(['a1', 'a2'])]).toEqual(['a1', 'a2'])
  })
})

describe('pruneSelection', () => {
  it('drops alerts a filter change removed from view', () => {
    expect([...pruneSelection(new Set(['a1', 'a2', 'a3']), ['a1', 'a3'])]).toEqual(['a1', 'a3'])
  })

  it('keeps the selection intact when everything is still visible', () => {
    expect([...pruneSelection(new Set(['a1']), ['a1', 'a2'])]).toEqual(['a1'])
  })

  it('empties the selection when a filter hides everything', () => {
    expect([...pruneSelection(new Set(['a1']), [])]).toEqual([])
  })
})

describe('clearSelection', () => {
  it('returns an empty selection', () => {
    expect(clearSelection().size).toBe(0)
  })
})

describe('describeSelection', () => {
  it('agrees in number for one alert', () => {
    expect(describeSelection(1)).toBe('1 alert selected')
  })

  it('pluralizes for many', () => {
    expect(describeSelection(12)).toBe('12 alerts selected')
  })
})
