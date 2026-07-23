import { describe, expect, it } from 'vitest'

import type { Relationship } from '../../api/contracts'
import {
  CLUSTER_COLOR_PALETTE,
  clusterColorFor,
  isPredictedRelationship,
  PREDICTED_LINK_COLOR,
  PREDICTED_LINK_DASH,
  predictedConfidenceFor,
} from '../graphStyles'

function rel(metadata: Record<string, unknown>): Relationship {
  return {
    id: 'rel-1',
    type: 'refers',
    source_id: 'a',
    target_id: 'b',
    properties: {},
    metadata,
    created_at: '2026-07-23T00:00:00Z',
    version: 1,
  } as Relationship
}

describe('clusterColorFor', () => {
  it('is deterministic for the same cluster id', () => {
    expect(clusterColorFor('community-5')).toBe(clusterColorFor('community-5'))
  })

  it('returns a palette color', () => {
    expect(CLUSTER_COLOR_PALETTE).toContain(clusterColorFor('community-5'))
  })

  it('spreads distinct ids across the palette', () => {
    const colors = new Set(
      ['c-1', 'c-2', 'c-3', 'c-4', 'c-5', 'c-6', 'c-7', 'c-8'].map(clusterColorFor),
    )
    expect(colors.size).toBeGreaterThan(1)
  })
})

describe('predicted relationship helpers', () => {
  it('detects metadata.predicted === true only', () => {
    expect(isPredictedRelationship(rel({ predicted: true }))).toBe(true)
    expect(isPredictedRelationship(rel({ predicted: 'yes' }))).toBe(false)
    expect(isPredictedRelationship(rel({}))).toBe(false)
  })

  it('clamps confidence to [0,1] and rejects non-numbers', () => {
    expect(predictedConfidenceFor(rel({ confidence: 0.8 }))).toBe(0.8)
    expect(predictedConfidenceFor(rel({ confidence: 7 }))).toBe(1)
    expect(predictedConfidenceFor(rel({ confidence: 'high' }))).toBeNull()
    expect(predictedConfidenceFor(rel({}))).toBeNull()
  })

  it('exports the dormant predicted-link style constants', () => {
    expect(PREDICTED_LINK_DASH).toEqual([4, 3])
    expect(PREDICTED_LINK_COLOR).toContain('168, 85, 247')
  })
})
