import { describe, expect, it } from 'vitest'

import { integerTicks } from '../axisTicks'

describe('integerTicks', () => {
  it('never produces a fractional tick', () => {
    for (const max of [0, 1, 2, 3, 7, 12, 40, 137, 1001]) {
      for (const tick of integerTicks(max)) {
        expect(Number.isInteger(tick), `tick ${tick} for max ${max}`).toBe(true)
      }
    }
  })

  it('counts one alert as 0 and 1, not 0.25 / 0.5 / 0.75', () => {
    // The Severity Mix axis rendered quarter-alert gridlines for a single
    // critical alert, which is meaningless for a count (UXA-203).
    expect(integerTicks(1)).toEqual([0, 1])
  })

  it('always starts at zero so bar heights are readable as magnitudes', () => {
    expect(integerTicks(9)[0]).toBe(0)
  })

  it('always includes a tick at or above the data maximum', () => {
    for (const max of [3, 7, 12, 40, 137]) {
      const ticks = integerTicks(max)
      expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(max)
    }
  })

  it('enumerates every value for small counts', () => {
    expect(integerTicks(3)).toEqual([0, 1, 2, 3])
  })

  it('keeps the tick count bounded for large maxima', () => {
    expect(integerTicks(1000).length).toBeLessThanOrEqual(6)
  })

  it('handles an all-zero series without collapsing the axis', () => {
    expect(integerTicks(0)).toEqual([0, 1])
  })

  it('is defensive about negative or non-finite maxima', () => {
    expect(integerTicks(-5)).toEqual([0, 1])
    expect(integerTicks(Number.NaN)).toEqual([0, 1])
  })
})
