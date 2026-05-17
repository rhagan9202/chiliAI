import { describe, expect, it, vi } from 'vitest'

import { apiPost, apiUpload } from '../client'
import {
  pushRecords,
  uploadRecordFile,
  usePushRecords,
  useUploadRecordFile,
} from '../records'
import type { RecordIngestReceipt, RecordPushRequest } from '../contracts'

vi.mock('../client', () => ({
  apiPost: vi.fn(),
  apiUpload: vi.fn(),
}))

const apiPostMock = vi.mocked(apiPost)
const apiUploadMock = vi.mocked(apiUpload)

describe('records API', () => {
  it('pushes structured records and resolves an ingest receipt', async () => {
    const payload: RecordPushRequest = {
      feed_name: 'claims_feed',
      rows: [{ claim_id: 'c1', anomaly_score: 0.8 }],
    }
    const receipt: RecordIngestReceipt = {
      knowledge_base_id: 'kb-1',
      feed_name: 'claims_feed',
      record_type: 'claim',
      correlation_id: 'corr-1',
      accepted_count: 1,
      created_at: '2026-05-16T12:00:00Z',
    }
    apiPostMock.mockResolvedValue(receipt)

    await expect(pushRecords('kb-1', payload)).resolves.toBe(receipt)

    expect(apiPostMock).toHaveBeenCalledWith('/records/kb-1/push', payload)
  })

  it('uploads a record file as form data with feed and original file', async () => {
    const file = new File(['claim_id,anomaly_score\nc1,0.8\n'], 'claims.csv', {
      type: 'text/csv',
    })
    const receipt: RecordIngestReceipt = {
      knowledge_base_id: 'kb-1',
      feed_name: 'claims_feed',
      record_type: 'claim',
      correlation_id: 'corr-1',
      accepted_count: 1,
      created_at: '2026-05-16T12:00:00Z',
    }
    apiUploadMock.mockResolvedValue(receipt)

    await expect(uploadRecordFile('kb-1', 'claims_feed', file)).resolves.toBe(receipt)

    expect(apiUploadMock).toHaveBeenCalledTimes(1)
    const [path, formData] = apiUploadMock.mock.calls[0]
    expect(path).toBe('/records/kb-1/files')
    expect(formData.get('feed')).toBe('claims_feed')
    expect(formData.get('file')).toBe(file)
  })

  it('exports records ingestion mutation hooks', () => {
    expect(typeof usePushRecords).toBe('function')
    expect(typeof useUploadRecordFile).toBe('function')
  })
})
