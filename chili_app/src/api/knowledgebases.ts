import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiDelete, apiFetch, apiPost, apiUploadWithProgress } from './client'
import type { UploadOptions } from './client'
import type {
  DocumentRegistrationResponse,
  KnowledgeBaseCreateRequest,
  KnowledgeBaseDocumentListResponse,
  KnowledgeBaseDocumentPreviewResponse,
  KnowledgeBaseListResponse,
  KnowledgeBaseSummaryResponse,
} from './contracts'

export const knowledgeBasesQueryKey = ['knowledge-bases'] as const

export interface KnowledgeBaseDocumentsOptions {
  limit?: number
  offset?: number
}

export function knowledgeBaseDetailQueryKey(knowledgeBaseId: string) {
  return ['knowledge-bases', knowledgeBaseId] as const
}

export function knowledgeBaseDocumentsQueryKey(
  knowledgeBaseId: string,
  options: KnowledgeBaseDocumentsOptions = {},
) {
  const hasPagination = options.limit !== undefined || options.offset !== undefined
  return hasPagination
    ? ['knowledge-bases', knowledgeBaseId, 'documents', options] as const
    : ['knowledge-bases', knowledgeBaseId, 'documents'] as const
}

export function knowledgeBaseDocumentPreviewQueryKey(
  knowledgeBaseId: string,
  documentId: string,
  options: { lineLimit?: number; charLimit?: number } = {},
) {
  const hasOptions = options.lineLimit !== undefined || options.charLimit !== undefined
  return hasOptions
    ? ['knowledge-bases', knowledgeBaseId, 'documents', documentId, 'preview', options] as const
    : ['knowledge-bases', knowledgeBaseId, 'documents', documentId, 'preview'] as const
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
  options: KnowledgeBaseDocumentsOptions = {},
): Promise<KnowledgeBaseDocumentListResponse> {
  const searchParams = new URLSearchParams()
  if (options.limit !== undefined) {
    searchParams.set('limit', String(options.limit))
  }
  if (options.offset !== undefined) {
    searchParams.set('offset', String(options.offset))
  }
  const queryString = searchParams.toString()
  const path = `/knowledgebases/${knowledgeBaseId}/documents${queryString ? `?${queryString}` : ''}`
  return apiFetch<KnowledgeBaseDocumentListResponse>(path)
}

export function deleteKnowledgeBaseDocument(
  knowledgeBaseId: string,
  documentId: string,
): Promise<void> {
  return apiDelete<void>(`/knowledgebases/${knowledgeBaseId}/documents/${documentId}`)
}

export function getKnowledgeBaseDocumentPreview(
  knowledgeBaseId: string,
  documentId: string,
  options: { lineLimit?: number; charLimit?: number } = {},
): Promise<KnowledgeBaseDocumentPreviewResponse> {
  const searchParams = new URLSearchParams()
  if (options.lineLimit !== undefined) {
    searchParams.set('line_limit', String(options.lineLimit))
  }
  if (options.charLimit !== undefined) {
    searchParams.set('char_limit', String(options.charLimit))
  }
  const queryString = searchParams.toString()
  const path = `/knowledgebases/${knowledgeBaseId}/documents/${documentId}/preview${queryString ? `?${queryString}` : ''}`
  return apiFetch<KnowledgeBaseDocumentPreviewResponse>(path)
}

export function uploadKnowledgeBaseDocuments(
  knowledgeBaseId: string,
  files: File[],
  options: UploadOptions = {},
): Promise<DocumentRegistrationResponse> {
  const formData = new FormData()
  files.forEach((file) => {
    formData.append('files', file)
  })
  return apiUploadWithProgress<DocumentRegistrationResponse>(
    `/knowledgebases/${knowledgeBaseId}/documents`,
    formData,
    options,
  )
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

export function useKnowledgeBaseDocuments(
  knowledgeBaseId: string | null,
  options: KnowledgeBaseDocumentsOptions = {},
) {
  return useQuery({
    queryKey: knowledgeBaseDocumentsQueryKey(knowledgeBaseId ?? 'missing', options),
    queryFn: () => getKnowledgeBaseDocuments(knowledgeBaseId ?? '', options),
    enabled: Boolean(knowledgeBaseId),
  })
}

export function useKnowledgeBaseDocumentPreview(
  knowledgeBaseId: string | null,
  documentId: string | null,
  options: { lineLimit?: number; charLimit?: number } = {},
) {
  return useQuery({
    queryKey: knowledgeBaseDocumentPreviewQueryKey(
      knowledgeBaseId ?? 'missing',
      documentId ?? 'missing',
      options,
    ),
    queryFn: () => getKnowledgeBaseDocumentPreview(knowledgeBaseId ?? '', documentId ?? '', options),
    enabled: Boolean(knowledgeBaseId) && Boolean(documentId),
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

export type UploadKnowledgeBaseDocumentsVariables = {
  files: File[]
  onUploadProgress?: (percent: number) => void
}

export function useUploadKnowledgeBaseDocuments(knowledgeBaseId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ files, onUploadProgress }: UploadKnowledgeBaseDocumentsVariables) =>
      uploadKnowledgeBaseDocuments(knowledgeBaseId ?? '', files, { onUploadProgress }),
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
