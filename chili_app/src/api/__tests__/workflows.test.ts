import { describe, expect, it, vi } from 'vitest'

import { apiFetch } from '../client'
import { getWorkflows, workflowsListQueryKey, workflowsQueryKey } from '../workflows'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('workflows API', () => {
  it('exposes a stable query key', () => {
    expect(workflowsQueryKey).toEqual(['workflows'])
    expect(workflowsListQueryKey({ knowledgeBaseId: 'kb-1' })).toEqual([
      'workflows',
      { knowledgeBaseId: 'kb-1' },
    ])
  })

  it('fetches workflow summaries from the expected path', async () => {
    apiFetchMock.mockResolvedValue({ items: [] })

    await getWorkflows()

    expect(apiFetchMock).toHaveBeenCalledWith('/workflows')
  })

  it('serializes workflow filters as query parameters', async () => {
    apiFetchMock.mockResolvedValue({ items: [] })

    await getWorkflows({
      knowledgeBaseId: 'kb-1',
      status: 'running',
      limit: 25,
      offset: 50,
    })

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/workflows?knowledge_base_id=kb-1&status=running&limit=25&offset=50',
    )
  })
})
