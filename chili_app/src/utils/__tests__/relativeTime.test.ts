import { describe, expect, it } from 'vitest'

import { absoluteTime, relativeAge } from '../relativeTime'

const NOW = new Date('2026-07-27T12:00:00Z')

describe('relativeAge', () => {
  it('reads as just now under a minute', () => {
    expect(relativeAge('2026-07-27T11:59:30Z', NOW)).toBe('just now')
  })

  it('counts whole minutes', () => {
    expect(relativeAge('2026-07-27T11:57:00Z', NOW)).toBe('3m ago')
  })

  it('counts whole hours', () => {
    expect(relativeAge('2026-07-27T09:00:00Z', NOW)).toBe('3h ago')
  })

  it('counts whole days', () => {
    expect(relativeAge('2026-07-25T12:00:00Z', NOW)).toBe('2d ago')
  })

  it('switches to weeks past a fortnight so a queue does not read "43d ago"', () => {
    expect(relativeAge('2026-06-27T12:00:00Z', NOW)).toBe('4w ago')
  })

  it('returns an empty string for an unparseable timestamp', () => {
    expect(relativeAge('not a date', NOW)).toBe('')
  })

  it('does not claim a future timestamp is old', () => {
    expect(relativeAge('2026-07-27T12:05:00Z', NOW)).toBe('just now')
  })
})

describe('absoluteTime', () => {
  it('spells out the timestamp for the hover title', () => {
    expect(absoluteTime('2026-07-27T09:05:00Z')).toBe('Jul 27, 2026, 09:05 UTC')
  })

  it('returns an empty string for an unparseable timestamp', () => {
    expect(absoluteTime('not a date')).toBe('')
  })
})
