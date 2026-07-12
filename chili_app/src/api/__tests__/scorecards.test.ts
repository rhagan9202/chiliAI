import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  exportScorecardRun,
  getScorecardRun,
  getScorecardRuns,
  scorecardRunQueryKey,
  scorecardRunsQueryKey,
} from '../scorecards'
import { apiFetch } from '../client'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('scorecards API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('exposes stable query keys with filters', () => {
    const filters = {
      knowledgeBaseId: 'kb-1',
      templateId: 'uh_scorecard',
      status: 'generated',
      limit: 10,
      offset: 20,
    } as const

    expect(scorecardRunsQueryKey(filters)).toEqual(['scorecards', 'runs', filters])
    expect(scorecardRunQueryKey('kb-1', 'run-1')).toEqual(['scorecards', 'runs', 'kb-1', 'run-1'])
  })

  it('fetches filtered runs, run detail, and exports with encoded params', async () => {
    apiFetchMock.mockResolvedValue({})

    await getScorecardRuns({
      knowledgeBaseId: 'kb 1',
      templateId: 'template/1',
      status: 'generated',
      limit: 10,
      offset: 20,
    })
    await getScorecardRun('kb 1', 'run/1')
    await exportScorecardRun('kb 1', 'run/1', 'markdown')

    expect(apiFetchMock).toHaveBeenNthCalledWith(
      1,
      '/scorecards/runs?knowledge_base_id=kb+1&template_id=template%2F1&status=generated&limit=10&offset=20',
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      2,
      '/scorecards/runs/run%2F1?knowledge_base_id=kb+1',
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      3,
      '/scorecards/runs/run%2F1/export?knowledge_base_id=kb+1&format=markdown',
    )
  })

  it('defaults exports to the json format', async () => {
    apiFetchMock.mockResolvedValue({})

    await exportScorecardRun('kb-1', 'run-1')

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/scorecards/runs/run-1/export?knowledge_base_id=kb-1&format=json',
    )
  })
})
