import { describe, expect, it, vi } from 'vitest'

import {
  addCaseFeedback,
  caseDetailQueryKey,
  casesQueryKey,
  createCase,
  getCase,
  getCases,
  promoteCase,
  updateCase,
} from '../cases'
import { apiFetch, apiPatch, apiPost } from '../client'
import type {
  CaseCreateRequest,
  CaseFeedbackCreateRequest,
  CasePromoteRequest,
  CaseUpdateRequest,
} from '../contracts'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)
const apiPatchMock = vi.mocked(apiPatch)
const apiPostMock = vi.mocked(apiPost)

describe('cases API', () => {
  it('exposes stable KB-scoped query keys', () => {
    expect(casesQueryKey('kb-1')).toEqual(['cases', 'kb-1'])
    expect(caseDetailQueryKey('kb-1', 'case-1')).toEqual(['cases', 'kb-1', 'case-1'])
  })

  it('fetches case lists and details scoped by knowledge base', async () => {
    apiFetchMock.mockResolvedValueOnce({ items: [], page: { page: 1, page_size: 25, total_items: 0 } })
    apiFetchMock.mockResolvedValueOnce({ case: { id: 'case-1' } })

    await getCases('kb-1')
    await getCase('kb-1', 'case-1')

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/cases?knowledge_base_id=kb-1')
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/cases/case-1?knowledge_base_id=kb-1')
  })

  it('creates, updates, promotes, and appends feedback scoped by knowledge base', async () => {
    const createPayload: CaseCreateRequest = {
      title: 'Escalation',
      priority: 'high',
      alert_ids: ['alert-1'],
    }
    const updatePayload: CaseUpdateRequest = { status: 'in_review' }
    const promotePayload: CasePromoteRequest = { alert_id: 'alert-1' }
    const feedbackPayload: CaseFeedbackCreateRequest = {
      label: 'suspicious',
      evidence_adequacy: 'high',
      missing_evidence: [],
      notes: 'Ready for review.',
    }
    apiPostMock.mockResolvedValue({ case: { id: 'case-1' } })
    apiPatchMock.mockResolvedValue({ case: { id: 'case-1' } })

    await createCase('kb-1', createPayload)
    await updateCase('kb-1', 'case-1', updatePayload)
    await promoteCase('kb-1', promotePayload)
    await addCaseFeedback('kb-1', 'case-1', feedbackPayload)

    expect(apiPostMock).toHaveBeenNthCalledWith(1, '/cases?knowledge_base_id=kb-1', createPayload)
    expect(apiPatchMock).toHaveBeenCalledWith('/cases/case-1?knowledge_base_id=kb-1', updatePayload)
    expect(apiPostMock).toHaveBeenNthCalledWith(2, '/cases/promote?knowledge_base_id=kb-1', promotePayload)
    expect(apiPostMock).toHaveBeenNthCalledWith(
      3,
      '/cases/case-1/feedback?knowledge_base_id=kb-1',
      feedbackPayload,
    )
  })
})
