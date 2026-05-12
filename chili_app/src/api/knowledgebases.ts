import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiDelete, apiFetch, apiPost, apiUpload } from './client'
import type {
  DocumentRegistrationResponse,
  KnowledgeBaseCreateRequest,
  KnowledgeBaseDocumentListResponse,
  KnowledgeBaseListResponse,
  KnowledgeBaseSummaryResponse,
} from './contracts'

export const knowledgeBasesQueryKey = ['knowledge-bases'] as const

export function knowledgeBaseDetailQueryKey(knowledgeBaseId: string) {
  return ['knowledge-bases', knowledgeBaseId] as const
}

export function knowledgeBaseDocumentsQueryKey(knowledgeBaseId: string) {
  return ['knowledge-bases', knowledgeBaseId, 'documents'] as const
}

export function getKnowledgeBases(): Promise<KnowledgeBaseListResponse> {
  return apiFetch<KnowledgeBaseListResponse>('/knowledgebases')
}

export function getKnowledgeBase(
  knowledgeBaseId: string,
): Promise<KnowledgeBaseSummaryResponse> {
  return apiFetch<KnowledgeBaseSummaryResponse>(`/knowledgebases/${knowledgeBaseId}`)
}

export function createKnowledgeBase(
  payload: KnowledgeBaseCreateRequest,
): Promise<KnowledgeBaseSummaryResponse> {
  return apiPost<KnowledgeBaseSummaryResponse, KnowledgeBaseCreateRequest>('/knowledgebases', payload)
}

export function deleteKnowledgeBase(knowledgeBaseId: string): Promise<void> {
  return apiDelete<void>(`/knowledgebases/${knowledgeBaseId}`)
}

export function getKnowledgeBaseDocuments(
  knowledgeBaseId: string,
): Promise<KnowledgeBaseDocumentListResponse> {
  return apiFetch<KnowledgeBaseDocumentListResponse>(`/knowledgebases/${knowledgeBaseId}/documents`)
}

export function deleteKnowledgeBaseDocument(
  knowledgeBaseId: string,
  documentId: string,
): Promise<void> {
  return apiDelete<void>(`/knowledgebases/${knowledgeBaseId}/documents/${documentId}`)
}

export function uploadKnowledgeBaseDocuments(
  knowledgeBaseId: string,
  files: File[],
): Promise<DocumentRegistrationResponse> {
  const formData = new FormData()
  files.forEach((file) => {
    formData.append('files', file)
  })
  return apiUpload<DocumentRegistrationResponse>(`/knowledgebases/${knowledgeBaseId}/documents`, formData)
}

export function useKnowledgeBases() {
  return useQuery({
    queryKey: knowledgeBasesQueryKey,
    queryFn: getKnowledgeBases,
  })
}

export function useKnowledgeBase(knowledgeBaseId: string | null) {
  return useQuery({
    queryKey: knowledgeBaseDetailQueryKey(knowledgeBaseId ?? 'missing'),
    queryFn: () => getKnowledgeBase(knowledgeBaseId ?? ''),
    enabled: Boolean(knowledgeBaseId),
  })
}

export function useKnowledgeBaseDocuments(knowledgeBaseId: string | null) {
  return useQuery({
    queryKey: knowledgeBaseDocumentsQueryKey(knowledgeBaseId ?? 'missing'),
    queryFn: () => getKnowledgeBaseDocuments(knowledgeBaseId ?? ''),
    enabled: Boolean(knowledgeBaseId),
  })
}

export function useCreateKnowledgeBase() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: createKnowledgeBase,
    onSuccess: (knowledgeBase) => {
      void queryClient.invalidateQueries({ queryKey: knowledgeBasesQueryKey })
      queryClient.setQueryData(
        knowledgeBaseDetailQueryKey(knowledgeBase.id),
        knowledgeBase,
      )
    },
  })
}

export function useDeleteKnowledgeBase() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: deleteKnowledgeBase,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: knowledgeBasesQueryKey })
    },
  })
}

export function useUploadKnowledgeBaseDocuments(knowledgeBaseId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (files: File[]) => uploadKnowledgeBaseDocuments(knowledgeBaseId ?? '', files),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: knowledgeBasesQueryKey })
      if (knowledgeBaseId) {
        void queryClient.invalidateQueries({ queryKey: knowledgeBaseDetailQueryKey(knowledgeBaseId) })
        void queryClient.invalidateQueries({ queryKey: knowledgeBaseDocumentsQueryKey(knowledgeBaseId) })
      }
    },
  })
}

export function useDeleteKnowledgeBaseDocument(knowledgeBaseId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (documentId: string) => deleteKnowledgeBaseDocument(knowledgeBaseId ?? '', documentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: knowledgeBasesQueryKey })
      if (knowledgeBaseId) {
        void queryClient.invalidateQueries({ queryKey: knowledgeBaseDetailQueryKey(knowledgeBaseId) })
        void queryClient.invalidateQueries({ queryKey: knowledgeBaseDocumentsQueryKey(knowledgeBaseId) })
      }
    },
  })
}
