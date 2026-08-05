import { useQuery } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type {
  PlaybookExportResponse,
  PlaybookImportRequestPayload,
  PlaybookImportResponse,
  PlaybookListResponse,
  PlaybookPublishRequestPayload,
  PlaybookSnapshotResponse,
} from './contracts'

export function playbooksQueryKey(knowledgeBaseId: string | null) {
  return ['playbooks', knowledgeBaseId ?? 'missing'] as const
}

export function listPlaybooks(
  knowledgeBaseId: string,
  limit = 50,
  offset = 0,
): Promise<PlaybookListResponse> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  return apiFetch<PlaybookListResponse>(
    `/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/playbooks?${params}`,
  )
}

export function publishPlaybook(
  knowledgeBaseId: string,
  playbookId: string,
  payload: PlaybookPublishRequestPayload,
): Promise<PlaybookSnapshotResponse> {
  return apiPost<PlaybookSnapshotResponse, PlaybookPublishRequestPayload>(
    `/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/playbooks/${encodeURIComponent(playbookId)}/publish`,
    payload,
  )
}

export function importPlaybooks(
  knowledgeBaseId: string,
  payload: PlaybookImportRequestPayload,
): Promise<PlaybookImportResponse> {
  return apiPost<PlaybookImportResponse, PlaybookImportRequestPayload>(
    `/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/playbooks/import`,
    payload,
  )
}

export function exportPlaybooks(knowledgeBaseId: string): Promise<PlaybookExportResponse> {
  return apiFetch<PlaybookExportResponse>(
    `/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/playbooks/export`,
  )
}

export function usePlaybooks(knowledgeBaseId: string | null, enabled = true) {
  return useQuery({
    queryKey: playbooksQueryKey(knowledgeBaseId),
    queryFn: () => listPlaybooks(knowledgeBaseId ?? ''),
    enabled: enabled && Boolean(knowledgeBaseId),
  })
}
