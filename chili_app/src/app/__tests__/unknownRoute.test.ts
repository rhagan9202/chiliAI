import { describe, expect, it } from 'vitest'

import { describeUnknownRoute } from '../unknownRoute'

const CONFIGURED = ['/dashboard', '/alerts', '/scorecards'] as const

describe('describeUnknownRoute', () => {
  it('treats a mistyped address as not found and quotes it back', () => {
    const copy = describeUnknownRoute('/alertz', CONFIGURED)

    expect(copy.title).toBe('Page not found')
    expect(copy.description).toContain('/alertz')
  })

  it('does not blame the domain configuration for a mistyped address', () => {
    const copy = describeUnknownRoute('/alertz', CONFIGURED)

    expect(copy.description).not.toMatch(/domain config/i)
  })

  it('explains that a configured page is simply not built yet', () => {
    const copy = describeUnknownRoute('/scorecards', CONFIGURED)

    expect(copy.title).toBe('Not available yet')
    expect(copy.description).toMatch(/not been built/i)
  })

  it('matches a configured page when the address has a trailing segment', () => {
    const copy = describeUnknownRoute('/scorecards/run-7', CONFIGURED)

    expect(copy.title).toBe('Not available yet')
  })

  it('falls back to not found when no routes are configured', () => {
    const copy = describeUnknownRoute('/anything', [])

    expect(copy.title).toBe('Page not found')
  })
})
