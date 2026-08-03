import { describe, expect, it, vi } from 'vitest'

import { apiFetch, apiPost } from '../client'
import {
  cancelScoreRun,
  getScoreRun,
  getScoreRuns,
  replayScoreRun,
  scoreRunQueryKey,
  scoreRunsQueryKey,
  startScoreRun,
} from '../scoreRuns'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
  apiPost: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)
const apiPostMock = vi.mocked(apiPost)

describe('score runs API', () => {
  it('exposes stable knowledge-base scoped query keys', () => {
    expect(scoreRunsQueryKey('kb-1', { limit: 1 })).toEqual([
      'knowledge-bases',
      'kb-1',
      'score-runs',
      { limit: 1 },
    ])
    expect(scoreRunQueryKey('kb-1', 'run-1')).toEqual([
      'knowledge-bases',
      'kb-1',
      'score-runs',
      'run-1',
    ])
  })

  it('lists score runs with pagination options', async () => {
    apiFetchMock.mockResolvedValue({ items: [], total: 0, limit: 1, offset: 0 })

    await getScoreRuns('kb-1', { limit: 1, offset: 0 })

    expect(apiFetchMock).toHaveBeenCalledWith('/knowledgebases/kb-1/score-runs?limit=1&offset=0')
  })

  it('starts a score run through the knowledge-base scoped route', async () => {
    apiPostMock.mockResolvedValue({ run: { id: 'run-1' }, batches: [], created: true })

    const payload = {
      batch_size: 100,
      catalog_version: 'catalog-2026-08',
      entity_ids: ['entity-1'],
      model_version: 'risk-v1',
      requested_by: 'analyst@example.test',
    }
    await startScoreRun('kb/needs encoding', payload)

    expect(apiPostMock).toHaveBeenCalledWith(
      '/knowledgebases/kb%2Fneeds%20encoding/score-runs',
      payload,
    )
  })

  it('fetches, cancels, and replays score runs through run scoped routes', async () => {
    apiFetchMock.mockResolvedValue({ run: { id: 'run-1' }, batches: [], created: false })
    apiPostMock.mockResolvedValue({ run: { id: 'run-1' }, batches: [], created: false })

    await getScoreRun('kb-1', 'run/1')
    await cancelScoreRun('kb-1', 'run/1')
    await replayScoreRun('kb-1', 'run/1', { requested_by: 'reviewer' })

    expect(apiFetchMock).toHaveBeenCalledWith('/knowledgebases/kb-1/score-runs/run%2F1')
    expect(apiPostMock).toHaveBeenCalledWith(
      '/knowledgebases/kb-1/score-runs/run%2F1/cancel',
      {},
    )
    expect(apiPostMock).toHaveBeenCalledWith(
      '/knowledgebases/kb-1/score-runs/run%2F1/replay',
      { requested_by: 'reviewer' },
    )
  })
})
