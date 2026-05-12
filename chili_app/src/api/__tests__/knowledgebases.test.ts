import { describe, expect, it, vi } from 'vitest'

import { apiDelete } from '../client'
import { deleteKnowledgeBase, deleteKnowledgeBaseDocument } from '../knowledgebases'

vi.mock('../client', () => ({
  apiDelete: vi.fn(),
  apiFetch: vi.fn(),
  apiPost: vi.fn(),
  apiUpload: vi.fn(),
}))

const apiDeleteMock = vi.mocked(apiDelete)

describe('knowledge bases API deletes', () => {
  it('returns void for backend 204 knowledge-base deletion responses', async () => {
    apiDeleteMock.mockResolvedValue(undefined)

    await expect(deleteKnowledgeBase('kb-1')).resolves.toBeUndefined()

    expect(apiDeleteMock).toHaveBeenCalledWith('/knowledgebases/kb-1')
  })

  it('returns void for backend 204 document deletion responses', async () => {
    apiDeleteMock.mockResolvedValue(undefined)

    await expect(deleteKnowledgeBaseDocument('kb-1', 'doc-1')).resolves.toBeUndefined()

    expect(apiDeleteMock).toHaveBeenCalledWith('/knowledgebases/kb-1/documents/doc-1')
  })
})
