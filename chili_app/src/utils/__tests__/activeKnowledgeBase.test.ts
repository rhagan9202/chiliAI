import { describe, expect, it } from 'vitest'

import type { KnowledgeBaseSummaryResponse } from '../../api/contracts'
import { resolveActiveKnowledgeBaseId } from '../activeKnowledgeBase'

function kb(
  overrides: Partial<KnowledgeBaseSummaryResponse> &
    Pick<KnowledgeBaseSummaryResponse, 'id'>,
): KnowledgeBaseSummaryResponse {
  return {
    name: overrides.id,
    description: '',
    entity_count: 0,
    relationship_count: 0,
    document_count: 0,
    status: 'ready',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: null,
    domain: 'medicare_fraud',
    ...overrides,
  }
}

const medicareKb = kb({ id: 'medicare-kb', domain: 'medicare_fraud' })
const housingKb = kb({ id: 'housing-kb', domain: 'af_housing' })

describe('resolveActiveKnowledgeBaseId', () => {
  it('picks the most recently updated knowledge base in the active domain', () => {
    const resolved = resolveActiveKnowledgeBaseId({
      knowledgeBases: [
        kb({ id: 'older', updated_at: '2026-03-01T00:00:00Z' }),
        kb({ id: 'newest', updated_at: '2026-07-01T00:00:00Z' }),
        kb({ id: 'oldest', updated_at: '2026-02-01T00:00:00Z' }),
      ],
      activeDomainName: 'medicare_fraud',
      requestedId: null,
      storedId: null,
    })

    expect(resolved).toBe('newest')
  })

  it('never selects a knowledge base stamped with a different domain', () => {
    const resolved = resolveActiveKnowledgeBaseId({
      knowledgeBases: [housingKb, medicareKb],
      activeDomainName: 'medicare_fraud',
      requestedId: null,
      storedId: null,
    })

    expect(resolved).toBe('medicare-kb')
  })

  it('treats an unstamped legacy knowledge base as in-domain', () => {
    const resolved = resolveActiveKnowledgeBaseId({
      knowledgeBases: [kb({ id: 'legacy', domain: null })],
      activeDomainName: 'medicare_fraud',
      requestedId: null,
      storedId: null,
    })

    expect(resolved).toBe('legacy')
  })

  it('uses the stored selection instead of the default when it is still available', () => {
    const resolved = resolveActiveKnowledgeBaseId({
      knowledgeBases: [
        kb({ id: 'stored', updated_at: '2026-02-01T00:00:00Z' }),
        kb({ id: 'newest', updated_at: '2026-07-01T00:00:00Z' }),
      ],
      activeDomainName: 'medicare_fraud',
      requestedId: null,
      storedId: 'stored',
    })

    expect(resolved).toBe('stored')
  })

  it('prefers the URL-requested knowledge base over the stored one', () => {
    const resolved = resolveActiveKnowledgeBaseId({
      // `stored` is also the most recent, so only the requested-wins rule
      // can produce `requested` here.
      knowledgeBases: [
        kb({ id: 'requested', updated_at: '2026-01-01T00:00:00Z' }),
        kb({ id: 'stored', updated_at: '2026-07-01T00:00:00Z' }),
      ],
      activeDomainName: 'medicare_fraud',
      requestedId: 'requested',
      storedId: 'stored',
    })

    expect(resolved).toBe('requested')
  })

  it('falls back to the default when the stored knowledge base no longer exists', () => {
    const resolved = resolveActiveKnowledgeBaseId({
      knowledgeBases: [
        kb({ id: 'stale', updated_at: '2026-01-01T00:00:00Z' }),
        kb({ id: 'survivor', updated_at: '2026-07-01T00:00:00Z' }),
      ],
      activeDomainName: 'medicare_fraud',
      requestedId: null,
      storedId: 'deleted-kb',
    })

    expect(resolved).toBe('survivor')
  })

  it('falls back to the default when the requested knowledge base is in another domain', () => {
    const resolved = resolveActiveKnowledgeBaseId({
      knowledgeBases: [housingKb, medicareKb],
      activeDomainName: 'medicare_fraud',
      requestedId: 'housing-kb',
      storedId: null,
    })

    expect(resolved).toBe('medicare-kb')
  })

  it('returns null when no knowledge base is available', () => {
    const resolved = resolveActiveKnowledgeBaseId({
      knowledgeBases: [],
      activeDomainName: 'medicare_fraud',
      requestedId: 'ghost',
      storedId: 'phantom',
    })

    expect(resolved).toBeNull()
  })

  it('prefers a ready knowledge base over a more recent one that is still building', () => {
    const resolved = resolveActiveKnowledgeBaseId({
      knowledgeBases: [
        kb({ id: 'building', status: 'building', updated_at: '2026-07-01T00:00:00Z' }),
        kb({ id: 'ready', status: 'ready', updated_at: '2026-03-01T00:00:00Z' }),
      ],
      activeDomainName: 'medicare_fraud',
      requestedId: null,
      storedId: null,
    })

    expect(resolved).toBe('ready')
  })

  it('falls back to a not-yet-ready knowledge base when none are ready', () => {
    const resolved = resolveActiveKnowledgeBaseId({
      knowledgeBases: [
        kb({ id: 'older-building', status: 'building', updated_at: '2026-01-01T00:00:00Z' }),
        kb({ id: 'newer-building', status: 'building', updated_at: '2026-07-01T00:00:00Z' }),
      ],
      activeDomainName: 'medicare_fraud',
      requestedId: null,
      storedId: null,
    })

    expect(resolved).toBe('newer-building')
  })

  it('still honors an explicit selection of a not-yet-ready knowledge base', () => {
    const resolved = resolveActiveKnowledgeBaseId({
      knowledgeBases: [
        kb({ id: 'ready', status: 'ready' }),
        kb({ id: 'building', status: 'building' }),
      ],
      activeDomainName: 'medicare_fraud',
      requestedId: 'building',
      storedId: null,
    })

    expect(resolved).toBe('building')
  })

  it('orders by creation time when a knowledge base has never been updated', () => {
    const resolved = resolveActiveKnowledgeBaseId({
      knowledgeBases: [
        kb({ id: 'created-later', created_at: '2026-06-01T00:00:00Z', updated_at: null }),
        kb({ id: 'created-earlier', created_at: '2026-01-01T00:00:00Z', updated_at: null }),
      ],
      activeDomainName: 'medicare_fraud',
      requestedId: null,
      storedId: null,
    })

    expect(resolved).toBe('created-later')
  })

  it('lets a knowledge base named by the route path win over ?kb= and the stored id', () => {
    expect(
      resolveActiveKnowledgeBaseId({
        knowledgeBases: [medicareKb, housingKb],
        activeDomainName: 'medicare_fraud',
        pathId: housingKb.id,
        requestedId: medicareKb.id,
        storedId: medicareKb.id,
      }),
    ).toBe(housingKb.id)
  })

  it('honours a path id from another domain — the workspace renders what the URL says', () => {
    // Domain scoping is warn-only (spec §1). Silently resolving to a different
    // corpus than the address bar names would make the header disagree with the
    // body it sits above.
    expect(
      resolveActiveKnowledgeBaseId({
        knowledgeBases: [medicareKb, housingKb],
        activeDomainName: 'medicare_fraud',
        pathId: housingKb.id,
        requestedId: null,
        storedId: null,
      }),
    ).toBe(housingKb.id)
  })

  it('falls through when the path names a knowledge base absent from the fetched page', () => {
    expect(
      resolveActiveKnowledgeBaseId({
        knowledgeBases: [medicareKb],
        activeDomainName: 'medicare_fraud',
        pathId: 'kb-deleted',
        requestedId: null,
        storedId: null,
      }),
    ).toBe(medicareKb.id)
  })
})
