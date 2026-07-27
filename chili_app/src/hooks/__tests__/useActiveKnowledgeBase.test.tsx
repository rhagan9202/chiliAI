import { renderHook, act } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { KnowledgeBaseSummaryResponse } from '../../api/contracts'
import { useDomainConfig } from '../../api/config'
import { useKnowledgeBases } from '../../api/knowledgebases'
import { useAppStore } from '../../stores/appStore'
import { useActiveKnowledgeBase } from '../useActiveKnowledgeBase'

vi.mock('../../api/knowledgebases', () => ({ useKnowledgeBases: vi.fn() }))
vi.mock('../../api/config', () => ({ useDomainConfig: vi.fn() }))

const useKnowledgeBasesMock = vi.mocked(useKnowledgeBases)
const useDomainConfigMock = vi.mocked(useDomainConfig)

function kb(
  id: string,
  overrides: Partial<KnowledgeBaseSummaryResponse> = {},
): KnowledgeBaseSummaryResponse {
  return {
    id,
    name: id,
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

function setKnowledgeBases(items: KnowledgeBaseSummaryResponse[]): void {
  // Only the fields the hook reads; the query result shape is large.
  useKnowledgeBasesMock.mockReturnValue({
    data: { items, total: items.length },
    isLoading: false,
  } as unknown as ReturnType<typeof useKnowledgeBases>)
}

function wrapper(initialEntry: string) {
  return ({ children }: { children: ReactNode }) =>
    createElement(MemoryRouter, { initialEntries: [initialEntry] }, children)
}

describe('useActiveKnowledgeBase', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useAppStore.setState({ activeKnowledgeBaseId: null })
    useDomainConfigMock.mockReturnValue({
      data: { domain: { name: 'medicare_fraud' } },
    } as unknown as ReturnType<typeof useDomainConfig>)
  })

  it('defaults to the most recently updated in-domain knowledge base', () => {
    setKnowledgeBases([
      kb('older', { updated_at: '2026-02-01T00:00:00Z' }),
      kb('newest', { updated_at: '2026-07-01T00:00:00Z' }),
    ])

    const { result } = renderHook(() => useActiveKnowledgeBase(), {
      wrapper: wrapper('/cases'),
    })

    expect(result.current.activeKnowledgeBaseId).toBe('newest')
  })

  it('honors an explicit ?kb= selection from the URL', () => {
    setKnowledgeBases([
      kb('linked', { updated_at: '2026-02-01T00:00:00Z' }),
      kb('newest', { updated_at: '2026-07-01T00:00:00Z' }),
    ])

    const { result } = renderHook(() => useActiveKnowledgeBase(), {
      wrapper: wrapper('/investigation/provider-1?kb=linked'),
    })

    expect(result.current.activeKnowledgeBaseId).toBe('linked')
  })

  it('remembers the resolved selection so other pages agree on it', () => {
    setKnowledgeBases([kb('linked'), kb('other')])

    renderHook(() => useActiveKnowledgeBase(), {
      wrapper: wrapper('/alerts?kb=linked'),
    })

    expect(useAppStore.getState().activeKnowledgeBaseId).toBe('linked')
  })

  it('setActiveKnowledgeBase persists the new selection', () => {
    setKnowledgeBases([kb('first'), kb('second')])

    const { result } = renderHook(() => useActiveKnowledgeBase(), {
      wrapper: wrapper('/cases'),
    })
    act(() => {
      result.current.setActiveKnowledgeBase('second')
    })

    expect(result.current.activeKnowledgeBaseId).toBe('second')
    expect(useAppStore.getState().activeKnowledgeBaseId).toBe('second')
  })

  it('exposes the in-domain knowledge bases for selector UIs', () => {
    setKnowledgeBases([
      kb('medicare-kb', { domain: 'medicare_fraud' }),
      kb('housing-kb', { domain: 'af_housing' }),
    ])

    const { result } = renderHook(() => useActiveKnowledgeBase(), {
      wrapper: wrapper('/cases'),
    })

    expect(result.current.knowledgeBases.map((item) => item.id)).toEqual(['medicare-kb'])
  })

  it('surfaces the inventory load state so pages can render loading and error', () => {
    useKnowledgeBasesMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useKnowledgeBases>)

    const { result } = renderHook(() => useActiveKnowledgeBase(), {
      wrapper: wrapper('/cases'),
    })

    expect(result.current.isError).toBe(true)
    expect(result.current.activeKnowledgeBaseId).toBeNull()
  })
})
