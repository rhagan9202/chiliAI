import type { Entity } from '../types/api'

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
