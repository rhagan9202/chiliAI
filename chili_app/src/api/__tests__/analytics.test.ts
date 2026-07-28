import { apiFetch } from '../client'
import {
  analyticsOverviewQueryKey,
  getAnalyticsOverview,
  getGnnClusters,
  getMetricTimeseries,
  getRiskScores,
} from '../analytics'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('analytics api helpers', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('scopes the overview to a knowledge base when one is active', async () => {
    apiFetchMock.mockResolvedValue({ active_alerts: 0 })

    await getAnalyticsOverview('kb-1')

    expect(apiFetchMock).toHaveBeenCalledWith('/analytics/overview?kb=kb-1')
  })

  it('omits the scope so the endpoint keeps its workspace-wide behaviour', async () => {
    apiFetchMock.mockResolvedValue({ active_alerts: 0 })

    await getAnalyticsOverview(null)

    expect(apiFetchMock).toHaveBeenCalledWith('/analytics/overview')
  })

  it('keys the overview query by knowledge base so switching refetches', () => {
    // Without the scope in the key, switching KBs would serve the previous
    // KB's cached totals (UXA-408).
    expect(analyticsOverviewQueryKey('kb-1')).not.toEqual(analyticsOverviewQueryKey('kb-2'))
  })

  it('serializes risk score collection filters', async () => {
    apiFetchMock.mockResolvedValue({ items: [] })

    await getRiskScores({ knowledgeBaseId: 'kb-1', entityType: 'provider', limit: 5 })

    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/analytics/risk-scores?knowledge_base_id=kb-1&entity_type=provider&limit=5'),
    )
  })

  it('serializes metric timeseries filters', async () => {
    apiFetchMock.mockResolvedValue({ metric: 'claim_volume', points: [] })

    await getMetricTimeseries({
      knowledgeBaseId: 'kb-1',
      metric: 'claim_volume',
      start: '2026-05-15T00:00:00.000Z',
      end: '2026-06-14T00:00:00.000Z',
    })

    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/analytics/timeseries?'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('knowledge_base_id=kb-1'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('metric=claim_volume'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('start=2026-05-15T00%3A00%3A00.000Z'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('end=2026-06-14T00%3A00%3A00.000Z'),
    )
  })

  it('serializes gnn cluster knowledge base filters', async () => {
    apiFetchMock.mockResolvedValue({ clusters: [] })

    await getGnnClusters('kb-1')

    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/analytics/gnn/clusters?knowledge_base_id=kb-1'),
    )
  })
})
