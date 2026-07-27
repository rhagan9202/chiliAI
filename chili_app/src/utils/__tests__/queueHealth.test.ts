import { describe, expect, it } from 'vitest'

import { backlogTrend, queueHealth, type QueueAlert } from '../queueHealth'

const NOW = new Date('2026-07-27T12:00:00Z')

function alert(overrides: Partial<QueueAlert> = {}): QueueAlert {
  return {
    status: 'open',
    created_at: '2026-07-27T10:00:00Z',
    updated_at: '2026-07-27T10:00:00Z',
    ...overrides,
  }
}

describe('queueHealth', () => {
  it('reports the age of the oldest alert still open', () => {
    const health = queueHealth(
      [
        alert({ created_at: '2026-07-27T09:00:00Z' }),
        alert({ created_at: '2026-07-25T12:00:00Z' }),
        // Already resolved, so it is not part of the backlog.
        alert({ status: 'resolved', created_at: '2026-07-01T12:00:00Z' }),
      ],
      NOW,
    )

    // Spelled out: these render in chips that uppercase, and "2D" is opaque.
    expect(health.oldestOpenAge).toBe('2 days')
  })

  it('says so plainly when nothing is waiting', () => {
    const health = queueHealth([alert({ status: 'resolved' })], NOW)

    expect(health.oldestOpenAge).toBeNull()
    expect(health.openCount).toBe(0)
  })

  it('measures the median time to acknowledge, not the mean', () => {
    // One outlier must not move the number a supervisor reads as typical.
    const health = queueHealth(
      [
        alert({
          status: 'acknowledged',
          created_at: '2026-07-27T10:00:00Z',
          updated_at: '2026-07-27T10:10:00Z',
        }),
        alert({
          status: 'acknowledged',
          created_at: '2026-07-27T10:00:00Z',
          updated_at: '2026-07-27T10:20:00Z',
        }),
        alert({
          status: 'acknowledged',
          created_at: '2026-07-27T10:00:00Z',
          updated_at: '2026-07-28T10:00:00Z',
        }),
      ],
      NOW,
    )

    expect(health.medianTimeToAcknowledge).toBe('20 min')
  })

  it('has no acknowledgement time when nothing has been acknowledged', () => {
    expect(queueHealth([alert()], NOW).medianTimeToAcknowledge).toBeNull()
  })

  it('counts what was dispositioned in the last day as throughput', () => {
    const health = queueHealth(
      [
        alert({ status: 'acknowledged', updated_at: '2026-07-27T11:00:00Z' }),
        alert({ status: 'resolved', updated_at: '2026-07-27T02:00:00Z' }),
        // Outside the window.
        alert({ status: 'resolved', updated_at: '2026-07-20T02:00:00Z' }),
        // Still open, so not throughput.
        alert({ status: 'open', updated_at: '2026-07-27T11:30:00Z' }),
      ],
      NOW,
    )

    expect(health.dispositionedLastDay).toBe(2)
  })
})

describe('backlogTrend', () => {
  it('buckets alerts by day across the requested window', () => {
    const trend = backlogTrend(
      [
        alert({ created_at: '2026-07-26T09:00:00Z' }),
        alert({ created_at: '2026-07-26T20:00:00Z' }),
        alert({ created_at: '2026-07-27T01:00:00Z' }),
      ],
      NOW,
      3,
    )

    expect(trend).toEqual([
      { label: 'Jul 25', value: 0 },
      { label: 'Jul 26', value: 2 },
      { label: 'Jul 27', value: 1 },
    ])
  })

  it('returns one bucket per day so the axis is never sparse', () => {
    expect(backlogTrend([], NOW, 7)).toHaveLength(7)
  })
})
