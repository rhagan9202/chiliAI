import { apiFetch } from '../client'
import { getGnnClusters, getMetricTimeseries, getRiskScores } from '../analytics'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('analytics api helpers', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('serializes risk score collection filters', async () => {
    apiFetchMock.mockResolvedValue({ items: [] })

    await getRiskScores({ knowledgeBaseId: 'kb-1', entityType: 'provider', limit: 5 })

    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/analytics/risk-scores?kb_id=kb-1&entity_type=provider&limit=5'),
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
      expect.stringContaining('kb_id=kb-1'),
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
      expect.stringContaining('/analytics/gnn/clusters?kb_id=kb-1'),
    )
  })
})
