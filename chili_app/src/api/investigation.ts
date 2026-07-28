import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type {
  EntityLocationListResponse,
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
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId, q: query })
  return apiFetch<InvestigationEntitySearchResponse>(`/investigation/search?${params}`)
}

export function getInvestigationEntity(
  knowledgeBaseId: string,
  entityId: string,
): Promise<InvestigationEntityDetailResponse> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
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
    knowledge_base_id: knowledgeBaseId,
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

export function entityLocationsQueryKey(entityId: string | null) {
  return ['investigation', 'entity-locations', entityId] as const
}

export function getEntityLocations(entityId: string): Promise<EntityLocationListResponse> {
  return apiFetch<EntityLocationListResponse>(
    `/investigation/entities/${encodeURIComponent(entityId)}/locate`,
  )
}

/**
 * Where an entity lives, asked only when the active KB does not hold it, so a
 * deep link with no `?kb=` can recover instead of dead-ending (UXA-104).
 */
export function useEntityLocations(entityId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: entityLocationsQueryKey(entityId),
    queryFn: () => getEntityLocations(entityId ?? ''),
    enabled: Boolean(entityId) && enabled,
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
    // Keep the previous entity visible while fetching the next one so the
    // page doesn't collapse in height and trigger an apparent scroll reset.
    placeholderData: (prev) => prev,
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
    // Keep the previous neighborhood graph visible during navigation so the
    // canvas maintains its height and pins survive the transition.
    placeholderData: (prev) => prev,
  })
}
