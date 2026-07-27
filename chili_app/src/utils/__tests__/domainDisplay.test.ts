import { describe, expect, it } from 'vitest'

import type { DomainConfig, RuntimeEntity } from '../../api/contracts'
import { getEntitySubtitle, getEntityTitle, getEntityTypeLabel } from '../domainDisplay'

/**
 * This ladder is mirrored in `backend/config/display.py::entity_display_label`
 * so an alert, a case title and the workbench heading cannot disagree about
 * what an entity is called (UXA-304). Changing it here means changing it there.
 */
const config = {
  entities: [{ name: 'provider', display_label: 'Provider', properties: {} }],
  relationships: [],
  ui: { display_fields: { provider: { title: 'npi', subtitle: 'specialty' } } },
} as unknown as DomainConfig

function entity(properties: Record<string, unknown>): RuntimeEntity {
  return { id: 'provider-1', type: 'provider', properties } as unknown as RuntimeEntity
}

describe('getEntityTitle', () => {
  it('uses the configured title property', () => {
    expect(getEntityTitle(entity({ npi: '1234567890' }), config)).toBe('1234567890')
  })

  it('falls back to a name property', () => {
    expect(getEntityTitle(entity({ name: 'Redwood DME Group' }), config)).toBe(
      'Redwood DME Group',
    )
  })

  it('falls back to the entity type label and id, never a bare identifier', () => {
    // A bare `provider-1` reads as an internal handle; the type label at least
    // says what the reader is looking at. The backend produces the same string.
    expect(getEntityTitle(entity({}), config)).toBe('Provider provider-1')
  })

  it('uses the raw type when the configuration does not declare it', () => {
    const ghost = { id: 'ghost-1', type: 'ghost', properties: {} } as unknown as RuntimeEntity

    expect(getEntityTitle(ghost, config)).toBe('ghost ghost-1')
  })
})

describe('getEntitySubtitle', () => {
  it('reads the configured subtitle property', () => {
    expect(getEntitySubtitle(entity({ specialty: 'Pain Management' }), config)).toBe(
      'Pain Management',
    )
  })

  it('returns null when the configured subtitle field is absent', () => {
    expect(getEntitySubtitle(entity({}), config)).toBeNull()
  })
})

describe('getEntityTypeLabel', () => {
  it('reads the configured display label', () => {
    expect(getEntityTypeLabel('provider', config)).toBe('Provider')
  })

  it('falls back to the raw type', () => {
    expect(getEntityTypeLabel('ghost', config)).toBe('ghost')
  })
})
