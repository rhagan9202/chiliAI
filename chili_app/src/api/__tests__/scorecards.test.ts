import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  exportScorecardRun,
  generateScorecardRun,
  getScorecardRun,
  getScorecardRuns,
  getScorecardTemplates,
  scorecardRunQueryKey,
  scorecardRunsQueryKey,
  scorecardTemplatesQueryKey,
} from '../scorecards'
import { apiFetch, apiPost } from '../client'
import type { ScorecardRunGenerateRequest } from '../contracts'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
  apiPost: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)
const apiPostMock = vi.mocked(apiPost)

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

    expect(scorecardTemplatesQueryKey()).toEqual(['scorecards', 'templates'])
    expect(scorecardRunsQueryKey(filters)).toEqual(['scorecards', 'runs', filters])
    expect(scorecardRunQueryKey('kb-1', 'run-1')).toEqual(['scorecards', 'runs', 'kb-1', 'run-1'])
  })

  it('fetches templates, filtered runs, run detail, and exports with encoded params', async () => {
    apiFetchMock.mockResolvedValue({})

    await getScorecardTemplates()
    await getScorecardRuns({
      knowledgeBaseId: 'kb 1',
      templateId: 'template/1',
      status: 'generated',
      limit: 10,
      offset: 20,
    })
    await getScorecardRun('kb 1', 'run/1')
    await exportScorecardRun('kb 1', 'run/1', 'markdown')

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/scorecards/templates')
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      2,
      '/scorecards/runs?knowledge_base_id=kb+1&template_id=template%2F1&status=generated&limit=10&offset=20',
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      3,
      '/scorecards/runs/run%2F1?knowledge_base_id=kb+1',
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      4,
      '/scorecards/runs/run%2F1/export?knowledge_base_id=kb+1&format=markdown',
    )
  })

  it('generates scorecard runs with apiPost and the JSON payload', async () => {
    const payload: ScorecardRunGenerateRequest = {
      knowledge_base_id: 'kb-1',
      template_id: 'uh_scorecard',
      scope_type: 'installation',
      scope_id: 'base-1',
      period_start: '2026-06-01',
      period_end: '2026-06-30',
    }
    apiPostMock.mockResolvedValue({ id: 'run-1' })

    await generateScorecardRun(payload)

    expect(apiPostMock).toHaveBeenCalledWith('/scorecards/runs', payload)
  })
})
