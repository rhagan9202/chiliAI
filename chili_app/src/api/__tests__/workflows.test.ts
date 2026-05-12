import { describe, expect, it, vi } from 'vitest'

import { apiFetch } from '../client'
import { getWorkflows, workflowsQueryKey } from '../workflows'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('workflows API', () => {
  it('exposes a stable query key', () => {
    expect(workflowsQueryKey).toEqual(['workflows'])
  })

  it('fetches workflow summaries from the expected path', async () => {
    apiFetchMock.mockResolvedValue({ items: [] })

    await getWorkflows()

    expect(apiFetchMock).toHaveBeenCalledWith('/workflows')
  })
})
