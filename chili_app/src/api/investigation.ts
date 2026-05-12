import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type {
  InvestigationEntityDetailResponse,
  InvestigationEntitySearchResponse,
  InvestigationNeighborhoodResponse,
} from './contracts'

export function investigationSearchQueryKey(
  knowledgeBaseId: string | null,
  query: string,
) {
  return ['investigation', 'search', knowledgeBaseId ?? 'missing', query] as const
}

export function investigationEntityQueryKey(
  knowledgeBaseId: string | null,
  entityId: string | null,
) {
  return ['investigation', 'entity', knowledgeBaseId ?? 'missing', entityId ?? 'missing'] as const
}

export function investigationNeighborhoodQueryKey(
  knowledgeBaseId: string | null,
  entityId: string | null,
  depth: number,
) {
  return [
    'investigation',
    'neighborhood',
    knowledgeBaseId ?? 'missing',
    entityId ?? 'missing',
    depth,
  ] as const
}

export function searchInvestigationEntities(
  knowledgeBaseId: string,
  query: string,
): Promise<InvestigationEntitySearchResponse> {
  const params = new URLSearchParams({ kb_id: knowledgeBaseId, q: query })
  return apiFetch<InvestigationEntitySearchResponse>(`/investigation/search?${params}`)
}

export function getInvestigationEntity(
  knowledgeBaseId: string,
  entityId: string,
): Promise<InvestigationEntityDetailResponse> {
  const params = new URLSearchParams({ kb_id: knowledgeBaseId })
  return apiFetch<InvestigationEntityDetailResponse>(
    `/investigation/entities/${encodeURIComponent(entityId)}?${params}`,
  )
}

export function getInvestigationNeighborhood(
  knowledgeBaseId: string,
  entityId: string,
  depth: number,
): Promise<InvestigationNeighborhoodResponse> {
  const params = new URLSearchParams({
    kb_id: knowledgeBaseId,
    depth: String(depth),
  })
  return apiFetch<InvestigationNeighborhoodResponse>(
    `/investigation/entities/${encodeURIComponent(entityId)}/neighborhood?${params}`,
  )
}

export function useInvestigationEntitySearch(
  knowledgeBaseId: string | null,
  query: string,
) {
  const normalizedQuery = query.trim()
  return useQuery({
    queryKey: investigationSearchQueryKey(knowledgeBaseId, normalizedQuery),
    queryFn: () => searchInvestigationEntities(knowledgeBaseId ?? '', normalizedQuery),
    enabled: Boolean(knowledgeBaseId) && normalizedQuery.length > 0,
  })
}

export function useInvestigationEntity(
  knowledgeBaseId: string | null,
  entityId: string | null,
) {
  return useQuery({
    queryKey: investigationEntityQueryKey(knowledgeBaseId, entityId),
    queryFn: () => getInvestigationEntity(knowledgeBaseId ?? '', entityId ?? ''),
    enabled: Boolean(knowledgeBaseId) && Boolean(entityId),
  })
}

export function useInvestigationNeighborhood(
  knowledgeBaseId: string | null,
  entityId: string | null,
  depth: number,
) {
  return useQuery({
    queryKey: investigationNeighborhoodQueryKey(knowledgeBaseId, entityId, depth),
    queryFn: () => getInvestigationNeighborhood(knowledgeBaseId ?? '', entityId ?? '', depth),
    enabled: Boolean(knowledgeBaseId) && Boolean(entityId),
  })
}
