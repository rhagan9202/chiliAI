import { apiFetch } from '../client'
import {
  analyticsOverviewQueryKey,
  getAnalyticsOverview,
  getGnnClusters,
  getMetricTimeseries,
  getPeerAnalysis,
  getRiskProjections,
  getRiskScores,
  peerAnalysisQueryKey,
  riskProjectionsQueryKey,
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

    expect(apiFetchMock).toHaveBeenCalledWith('/analytics/overview?knowledge_base_id=kb-1')
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

  it('serializes risk projection filters', async () => {
    apiFetchMock.mockResolvedValue({ items: [] })

    await getRiskProjections({
      knowledgeBaseId: 'kb-1',
      entityType: 'provider',
      riskLevel: 'high',
      typologyId: 'upcoding',
      status: 'case_open',
      maxScoreAgeHours: 48,
      asOf: '2026-08-03T12:00:00.000Z',
      limit: 5,
      offset: 10,
    })

    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/analytics/risk-projections?'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('knowledge_base_id=kb-1'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('entity_type=provider'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('risk_level=high'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('typology_id=upcoding'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('status=case_open'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('max_score_age_hours=48'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('as_of=2026-08-03T12%3A00%3A00.000Z'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('limit=5'),
    )
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('offset=10'),
    )
  })

  it('keys risk projections by collection filters', () => {
    const base = riskProjectionsQueryKey({
      knowledgeBaseId: 'kb-1',
      entityType: 'provider',
      riskLevel: 'high',
      typologyId: 'upcoding',
      status: 'case_open',
      maxScoreAgeHours: 48,
      asOf: '2026-08-03T12:00:00.000Z',
      limit: 5,
      offset: 0,
    })

    expect(base).not.toEqual(riskProjectionsQueryKey({
      knowledgeBaseId: 'kb-1',
      entityType: 'claim',
      riskLevel: 'high',
      typologyId: 'upcoding',
      status: 'case_open',
      maxScoreAgeHours: 48,
      asOf: '2026-08-03T12:00:00.000Z',
      limit: 5,
      offset: 0,
    }))
    expect(base).not.toEqual(riskProjectionsQueryKey({
      knowledgeBaseId: 'kb-1',
      entityType: 'provider',
      riskLevel: 'high',
      typologyId: 'upcoding',
      status: 'case_open',
      maxScoreAgeHours: 24,
      asOf: '2026-08-03T12:00:00.000Z',
      limit: 5,
      offset: 0,
    }))
    expect(base).not.toEqual(riskProjectionsQueryKey({
      knowledgeBaseId: 'kb-1',
      entityType: 'provider',
      riskLevel: 'high',
      typologyId: 'upcoding',
      status: 'case_open',
      maxScoreAgeHours: 48,
      asOf: '2026-08-03T12:00:00.000Z',
      limit: 5,
      offset: 10,
    }))
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

  it('serializes peer-analysis knowledge base and metric filters', async () => {
    apiFetchMock.mockResolvedValue({ entity_id: 'provider-204', metrics: [] })

    await getPeerAnalysis({
      knowledgeBaseId: 'kb-1',
      entityId: 'provider-204',
      metric: 'weekly_provider_billing',
    })

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/analytics/peer-analysis/provider-204?knowledge_base_id=kb-1&metric=weekly_provider_billing',
    )
  })

  it('keys peer analysis by KB, entity, and metric so route changes refetch', () => {
    const base = peerAnalysisQueryKey({
      knowledgeBaseId: 'kb-1',
      entityId: 'provider-204',
      metric: 'weekly_provider_billing',
    })

    expect(base).not.toEqual(peerAnalysisQueryKey({
      knowledgeBaseId: 'kb-2',
      entityId: 'provider-204',
      metric: 'weekly_provider_billing',
    }))
    expect(base).not.toEqual(peerAnalysisQueryKey({
      knowledgeBaseId: 'kb-1',
      entityId: 'provider-999',
      metric: 'weekly_provider_billing',
    }))
    expect(base).not.toEqual(peerAnalysisQueryKey({
      knowledgeBaseId: 'kb-1',
      entityId: 'provider-204',
      metric: null,
    }))
  })
})
