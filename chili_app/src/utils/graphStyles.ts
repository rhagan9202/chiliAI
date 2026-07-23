import type { Entity, Relationship } from '../types/api'

export const ENTITY_COLOR_PALETTE: readonly string[] = [
  '#4f46e5',
  '#0891b2',
  '#16a34a',
  '#ea580c',
  '#db2777',
  '#7c3aed',
] as const

const FALLBACK_COLOR = '#94a3b8'

const NODE_SIZE_MIN = 4
const NODE_SIZE_MAX = 24

function fnv1aHash(value: string): number {
  let hash = 0x811c9dc5
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i)
    hash = (hash + ((hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24))) >>> 0
  }
  return hash >>> 0
}

export function colorForEntityType(
  type: string,
  knownTypes: readonly string[] = [],
): string {
  if (type.length === 0) return FALLBACK_COLOR
  const idx = knownTypes.indexOf(type)
  if (idx >= 0) {
    return ENTITY_COLOR_PALETTE[idx % ENTITY_COLOR_PALETTE.length]
  }
  const hash = fnv1aHash(type)
  return ENTITY_COLOR_PALETTE[hash % ENTITY_COLOR_PALETTE.length]
}

export function riskScoreFor(entity: Entity): number {
  const fromTop = entity.properties['risk_score']
  if (typeof fromTop === 'number' && Number.isFinite(fromTop)) {
    return clamp01(fromTop)
  }
  const fromMeta = entity.metadata['risk_score']
  if (typeof fromMeta === 'number' && Number.isFinite(fromMeta)) {
    return clamp01(fromMeta)
  }
  return 0
}

export function sizeForRiskScore(score: number): number {
  const bounded = clamp01(score)
  return NODE_SIZE_MIN + (NODE_SIZE_MAX - NODE_SIZE_MIN) * bounded
}

export function communityIdFor(entity: Entity): string | null {
  const candidate =
    entity.properties['community_id'] ?? entity.metadata['community_id']
  if (typeof candidate === 'string' && candidate.length > 0) return candidate
  if (typeof candidate === 'number' && Number.isFinite(candidate)) {
    return String(candidate)
  }
  return null
}

function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0
  if (value < 0) return 0
  if (value > 1) return 1
  return value
}

/** Distinct from ENTITY_COLOR_PALETTE so the two color systems never collide. */
export const CLUSTER_COLOR_PALETTE: readonly string[] = [
  '#00d4ff',
  '#a855f7',
  '#f59e0b',
  '#10b981',
  '#f43f5e',
  '#818cf8',
  '#f97316',
  '#2dd4bf',
]

export function clusterColorFor(clusterId: string): string {
  return CLUSTER_COLOR_PALETTE[fnv1aHash(clusterId) % CLUSTER_COLOR_PALETTE.length]
}

/** Dormant until the backend writes predicted-link metadata (see plan Global Constraints). */
export const PREDICTED_LINK_COLOR = 'rgba(168, 85, 247, 0.75)'
export const PREDICTED_LINK_DASH: readonly [number, number] = [4, 3]

export function isPredictedRelationship(relationship: Relationship): boolean {
  return relationship.metadata?.predicted === true
}

export function predictedConfidenceFor(relationship: Relationship): number | null {
  const raw = relationship.metadata?.confidence
  if (typeof raw !== 'number' || Number.isNaN(raw)) {
    return null
  }
  return clamp01(raw)
}
