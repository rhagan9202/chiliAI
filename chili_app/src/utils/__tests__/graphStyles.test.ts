import { describe, expect, it } from 'vitest'

import type { Entity, Relationship } from '../../types/api'
import {
  CLUSTER_COLOR_PALETTE,
  GRAPH_LABEL_MAX_CHARS,
  MAX_FIT_ZOOM,
  NODE_REL_SIZE,
  PREDICTED_LINK_COLOR,
  PREDICTED_LINK_DASH,
  clampFitZoom,
  clusterColorFor,
  communityIdFor,
  graphNodeLabel,
  isPredictedRelationship,
  linkDistanceFor,
  nodeRadiusFor,
  predictedConfidenceFor,
  riskScoreFor,
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

describe('nodeRadiusFor', () => {
  it('grows with the node value', () => {
    expect(nodeRadiusFor(24)).toBeGreaterThan(nodeRadiusFor(4))
  })

  it('matches the force-graph area-proportional sizing for nodeRelSize', () => {
    // react-force-graph draws a node whose *area* is proportional to `val`,
    // so radius = sqrt(val) * nodeRelSize. Link spacing has to use the same
    // formula or edges end up shorter than the circles that sit on them.
    expect(nodeRadiusFor(4)).toBeCloseTo(Math.sqrt(4) * NODE_REL_SIZE, 5)
  })
})

describe('linkDistanceFor', () => {
  it('keeps the edge longer than the two node radii it connects', () => {
    const distance = linkDistanceFor(24, 24)
    expect(distance).toBeGreaterThan(nodeRadiusFor(24) + nodeRadiusFor(24))
  })

  it('scales up for larger nodes so big circles cannot swallow their edge', () => {
    expect(linkDistanceFor(24, 24)).toBeGreaterThan(linkDistanceFor(4, 4))
  })

  it('leaves visible gap between the smallest nodes', () => {
    expect(linkDistanceFor(4, 4)).toBeGreaterThan(nodeRadiusFor(4) * 2)
  })
})

describe('clampFitZoom', () => {
  it('leaves a zoomed-out fit untouched', () => {
    expect(clampFitZoom(0.6)).toBeCloseTo(0.6, 5)
  })

  it('caps an over-magnified fit so tiny neighborhoods do not fill the canvas', () => {
    // zoomToFit on a 2-3 node graph would otherwise magnify until the nodes
    // are larger than the edges between them (UXA-202).
    expect(clampFitZoom(12)).toBe(MAX_FIT_ZOOM)
  })

  it('returns the cap exactly at the boundary', () => {
    expect(clampFitZoom(MAX_FIT_ZOOM)).toBe(MAX_FIT_ZOOM)
  })
})

describe('graphNodeLabel', () => {
  it('uses the entity id', () => {
    expect(graphNodeLabel('provider-1')).toBe('provider-1')
  })

  it('truncates long ids so labels cannot overlap into noise', () => {
    const label = graphNodeLabel('a'.repeat(60))
    expect(label.length).toBeLessThanOrEqual(GRAPH_LABEL_MAX_CHARS + 1)
    expect(label.endsWith('…')).toBe(true)
  })

  it('returns an empty label for a blank id rather than drawing nothing useful', () => {
    expect(graphNodeLabel('')).toBe('')
  })
})

describe('entities without a metadata block', () => {
  // `metadata` is optional on Entity — only `id` and `type` are required — so
  // both readers have to treat an absent block as "no value recorded" rather
  // than reaching into it.
  function bareEntity(properties: Record<string, unknown> = {}): Entity {
    return { id: 'e-1', type: 'provider', properties } as Entity
  }

  it('scores an entity with no metadata as zero risk instead of throwing', () => {
    expect(riskScoreFor(bareEntity())).toBe(0)
  })

  it('still prefers a top-level risk_score when metadata is absent', () => {
    expect(riskScoreFor(bareEntity({ risk_score: 0.5 }))).toBeCloseTo(0.5)
  })

  it('reports no community for an entity with no metadata', () => {
    expect(communityIdFor(bareEntity())).toBeNull()
  })

  it('still reads a top-level community_id when metadata is absent', () => {
    expect(communityIdFor(bareEntity({ community_id: 'c-7' }))).toBe('c-7')
  })
})
