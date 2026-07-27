import { describe, expect, it } from 'vitest'

import { countTone, severityTone } from '../severity'

describe('severityTone', () => {
  it('renders critical as danger', () => {
    expect(severityTone('critical')).toBe('danger')
  })

  it('renders high as danger too, so a high alert never reads as a warning', () => {
    expect(severityTone('high')).toBe('danger')
  })

  it('renders medium as warning', () => {
    expect(severityTone('medium')).toBe('warning')
  })

  it('renders low as informational rather than alarming', () => {
    expect(severityTone('low')).toBe('info')
  })

  it('is case-insensitive so API and display casing agree', () => {
    expect(severityTone('CRITICAL')).toBe(severityTone('critical'))
  })

  it('falls back to a neutral tone for an unknown severity', () => {
    expect(severityTone('bogus')).toBe('default')
  })

  it('gives the same severity the same tone regardless of caller', () => {
    // The workbench previously hardcoded `warning` for every alert severity
    // while the feed used red for critical — the same alert rendered two
    // different colours on two screens (UXA-205).
    const fromFeed = severityTone('critical')
    const fromWorkbench = severityTone('critical')
    expect(fromFeed).toBe(fromWorkbench)
  })
})

describe('countTone', () => {
  it('renders a zero count as neutral, not as a failure', () => {
    // "Failed workflows 0" in red reads as an error at a glance.
    expect(countTone(0, 'danger')).toBe('default')
  })

  it('keeps the intended tone for a non-zero count', () => {
    expect(countTone(3, 'danger')).toBe('danger')
  })

  it('treats a negative count as neutral', () => {
    expect(countTone(-1, 'warning')).toBe('default')
  })
})
