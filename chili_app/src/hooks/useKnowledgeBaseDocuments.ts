import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import type {
  UseMutationResult,
  UseQueryResult,
} from '@tanstack/react-query'

import { API_BASE_URL, ApiError, apiRequest } from '../lib/apiClient'
import type { DocumentListResponse } from '../types/api'
import { knowledgeBasesQueryKey } from './useKnowledgeBases'

export const ACCEPTED_DOCUMENT_EXTENSIONS = [
  '.txt',
  '.json',
  '.csv',
  '.xlsx',
  '.pdf',
  '.docx',
] as const

export const ACCEPTED_DOCUMENT_MIME_TYPES = [
  'text/plain',
  'application/json',
  'text/csv',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
] as const

export const MAX_DOCUMENT_SIZE_BYTES = 50 * 1024 * 1024

export function knowledgeBaseDocumentsQueryKey(
  kbId: string,
): readonly unknown[] {
  return ['knowledge-bases', kbId, 'documents'] as const
}

export interface UseKnowledgeBaseDocumentsOptions {
  enabled?: boolean
}

export function useKnowledgeBaseDocuments(
  kbId: string | undefined,
  options: UseKnowledgeBaseDocumentsOptions = {},
): UseQueryResult<DocumentListResponse, Error> {
  return useQuery<DocumentListResponse, Error>({
    queryKey: kbId
      ? knowledgeBaseDocumentsQueryKey(kbId)
      : ['knowledge-bases', 'documents', 'idle'],
    queryFn: () =>
      apiRequest<DocumentListResponse>(
        `/knowledgebases/${kbId ?? ''}/documents`,
      ),
    enabled: Boolean(kbId) && (options.enabled ?? true),
  })
}

export interface UploadDocumentVariables {
  file: File
  onProgress?: (percent: number) => void
}

interface UploadHandlerArgs {
  kbId: string
  vars: UploadDocumentVariables
}

function uploadDocument({
  kbId,
  vars,
}: UploadHandlerArgs): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open(
      'POST',
      `${API_BASE_URL}/knowledgebases/${kbId}/documents`,
      true,
    )
    xhr.responseType = 'json'

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && vars.onProgress) {
        vars.onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response as unknown)
      } else {
        const body: unknown =
          xhr.response ??
          (typeof xhr.responseText === 'string' ? xhr.responseText : null)
        const detailMessage =
          body && typeof body === 'object' && 'detail' in body
            ? String((body as { detail: unknown }).detail)
            : `Upload failed with status ${xhr.status}`
        reject(new ApiError(xhr.status, detailMessage, body))
      }
    }

    xhr.onerror = () => {
      reject(new ApiError(0, 'Network error during upload', null))
    }

    xhr.onabort = () => {
      reject(new ApiError(0, 'Upload aborted', null))
    }

    const form = new FormData()
    form.append('files', vars.file, vars.file.name)
    xhr.send(form)
  })
}

export function useUploadDocument(
  kbId: string,
): UseMutationResult<unknown, Error, UploadDocumentVariables> {
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, UploadDocumentVariables>({
    mutationFn: (vars) => uploadDocument({ kbId, vars }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: knowledgeBaseDocumentsQueryKey(kbId),
      })
      void queryClient.invalidateQueries({ queryKey: knowledgeBasesQueryKey })
    },
  })
}

export function useDeleteDocument(
  kbId: string,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: async (documentId: string) => {
      await apiRequest<unknown>(
        `/knowledgebases/${kbId}/documents/${documentId}`,
        { method: 'DELETE' },
      )
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: knowledgeBaseDocumentsQueryKey(kbId),
      })
      void queryClient.invalidateQueries({ queryKey: knowledgeBasesQueryKey })
    },
  })
}

export interface DocumentValidationResult {
  ok: boolean
  reason?: string
}

export function validateDocumentFile(file: File): DocumentValidationResult {
  if (file.size > MAX_DOCUMENT_SIZE_BYTES) {
    return {
      ok: false,
      reason: `File exceeds the 50 MB limit (${(
        file.size /
        (1024 * 1024)
      ).toFixed(1)} MB).`,
    }
  }
  const lowerName = file.name.toLowerCase()
  const extOk = ACCEPTED_DOCUMENT_EXTENSIONS.some((ext) =>
    lowerName.endsWith(ext),
  )
  if (!extOk) {
    return {
      ok: false,
      reason: `Unsupported file type. Allowed: ${ACCEPTED_DOCUMENT_EXTENSIONS.join(', ')}.`,
    }
  }
  return { ok: true }
}
