import { describe, expect, it, vi } from 'vitest'

import { apiFetch } from '../client'
import { getAlerts } from '../alerts'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
  apiPost: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('alerts api', () => {
  it('serializes alert feed filters into backend query parameters', async () => {
    apiFetchMock.mockResolvedValueOnce({
      items: [],
      page: { page: 3, page_size: 25, total_items: 0 },
    })

    await getAlerts({
      knowledgeBaseId: 'kb-1',
      status: 'open',
      limit: 25,
      offset: 50,
    })

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/alerts?knowledge_base_id=kb-1&status=open&limit=25&offset=50',
    )
  })
})
