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
      statuses: ['open', 'acknowledged'],
      severities: ['critical'],
      typologies: ['billing'],
      createdFrom: '2026-08-01',
      createdTo: '2026-08-03',
      evidence: 'with_evidence',
      freshness: 'fresh',
      limit: 25,
      offset: 50,
    })

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/alerts?knowledge_base_id=kb-1&status=open&status=acknowledged&severity=critical&typology=billing&from=2026-08-01&to=2026-08-03&evidence=with_evidence&freshness=fresh&limit=25&offset=50',
    )
  })
})
