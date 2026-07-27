import { describe, expect, it } from 'vitest'

import { transportDelta, transportValueLabel } from '../transportDelta'

const REDIS = {
  backend: 'redis',
  uri: 'redis://redis:6379',
  stream_prefix: 'chili',
  consumer_group: 'chili-workers',
}

describe('transportDelta', () => {
  it('reports no change when both sides match', () => {
    expect(transportDelta(REDIS, REDIS)).toEqual({ changes: [], severity: 'none' })
  })

  it('treats in_memory and in-memory as the same backend', () => {
    // DomainConfig.events spells it in_memory; EventBusSettings spells it
    // in-memory. Comparing raw strings would call every swap a change.
    const active = { ...REDIS, backend: 'in_memory', uri: null }
    const candidate = { ...REDIS, backend: 'in-memory', uri: null }

    expect(transportDelta(active, candidate).severity).toBe('none')
  })

  it('flags a changed consumer group as abandoning queued work', () => {
    const delta = transportDelta(REDIS, { ...REDIS, consumer_group: 'other-workers' })

    expect(delta.severity).toBe('changed')
    expect(delta.changes).toEqual([
      { field: 'consumer_group', from: 'chili-workers', to: 'other-workers' },
    ])
  })

  it('flags a move to in-memory as decoupling the API from the worker', () => {
    const delta = transportDelta(REDIS, { ...REDIS, backend: 'in-memory', uri: null })

    expect(delta.severity).toBe('decoupled')
    expect(delta.changes.map((change) => change.field)).toEqual(['backend', 'uri'])
  })

  it('flags a move away from in-memory as decoupling too', () => {
    const active = { ...REDIS, backend: 'in_memory', uri: null }

    expect(transportDelta(active, REDIS).severity).toBe('decoupled')
  })

  it('says nothing when either side is unknown', () => {
    // An invalid pack reports no transport; warning on it would invent a
    // difference that cannot be seen.
    expect(transportDelta(REDIS, null).severity).toBe('none')
    expect(transportDelta(null, REDIS).severity).toBe('none')
    expect(transportDelta(undefined, undefined).severity).toBe('none')
  })

  it('treats an absent uri and an empty uri as the same absence', () => {
    const withNull = { ...REDIS, backend: 'in-memory', uri: null }
    const withEmpty = { ...REDIS, backend: 'in-memory', uri: '' }

    expect(transportDelta(withNull, withEmpty).severity).toBe('none')
  })

  it('reports every differing field, not just the first', () => {
    const delta = transportDelta(REDIS, {
      backend: 'redis',
      uri: 'redis://other:6379',
      stream_prefix: 'other',
      consumer_group: 'other-workers',
    })

    expect(delta.changes.map((change) => change.field)).toEqual([
      'uri',
      'stream_prefix',
      'consumer_group',
    ])
  })
})

describe('transportValueLabel', () => {
  it('renders an absent value as a word rather than an empty cell', () => {
    expect(transportValueLabel('')).toBe('none')
    expect(transportValueLabel('redis')).toBe('redis')
  })
})
