import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'

import { apiPost, apiUpload } from './client'
import type { RecordIngestReceipt, RecordPushRequest } from './contracts'
import {
  knowledgeBaseDetailQueryKey,
  knowledgeBaseDocumentsQueryKey,
  knowledgeBasesQueryKey,
} from './knowledgebases'
import { workflowsQueryKey } from './workflows'

const analyticsQueryKey = ['analytics'] as const
const graphQueryKey = ['graph'] as const

function invalidateRecordsIngestionQueries(
  queryClient: QueryClient,
  knowledgeBaseId: string | null,
) {
  void queryClient.invalidateQueries({ queryKey: knowledgeBasesQueryKey })
  void queryClient.invalidateQueries({ queryKey: workflowsQueryKey })
  void queryClient.invalidateQueries({ queryKey: analyticsQueryKey })
  void queryClient.invalidateQueries({ queryKey: graphQueryKey })
  if (knowledgeBaseId) {
    void queryClient.invalidateQueries({ queryKey: knowledgeBaseDetailQueryKey(knowledgeBaseId) })
    void queryClient.invalidateQueries({ queryKey: knowledgeBaseDocumentsQueryKey(knowledgeBaseId) })
  }
}

export function pushRecords(
  knowledgeBaseId: string,
  payload: RecordPushRequest,
): Promise<RecordIngestReceipt> {
  return apiPost<RecordIngestReceipt, RecordPushRequest>(
    `/records/${knowledgeBaseId}/push`,
    payload,
  )
}

export function uploadRecordFile(
  knowledgeBaseId: string,
  feedName: string,
  file: File,
): Promise<RecordIngestReceipt> {
  const formData = new FormData()
  formData.append('feed', feedName)
  formData.append('file', file)
  return apiUpload<RecordIngestReceipt>(`/records/${knowledgeBaseId}/files`, formData)
}

export function usePushRecords(knowledgeBaseId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: RecordPushRequest) => pushRecords(knowledgeBaseId ?? '', payload),
    onSuccess: () => {
      invalidateRecordsIngestionQueries(queryClient, knowledgeBaseId)
    },
  })
}

export function useUploadRecordFile(knowledgeBaseId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ feedName, file }: { feedName: string; file: File }) =>
      uploadRecordFile(knowledgeBaseId ?? '', feedName, file),
    onSuccess: () => {
      invalidateRecordsIngestionQueries(queryClient, knowledgeBaseId)
    },
  })
}
