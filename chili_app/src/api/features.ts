import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type {
  EntityFeatureValueListResponse,
  FeatureCatalogResponse,
} from './contracts'

export function featureCatalogQueryKey(knowledgeBaseId: string | null) {
  return ['features', 'catalog', knowledgeBaseId] as const
}

export function entityFeatureValuesQueryKey(
  knowledgeBaseId: string | null,
  entityType: string | null,
  entityId: string | null,
) {
  return ['features', 'entity-values', knowledgeBaseId, entityType, entityId] as const
}

export function getFeatureCatalog(knowledgeBaseId: string): Promise<FeatureCatalogResponse> {
  return apiFetch<FeatureCatalogResponse>(
    `/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/features/catalog`,
  )
}

export function getEntityFeatureValues(
  knowledgeBaseId: string,
  entityType: string,
  entityId: string,
): Promise<EntityFeatureValueListResponse> {
  return apiFetch<EntityFeatureValueListResponse>(
    `/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/entities/${encodeURIComponent(
      entityType,
    )}/${encodeURIComponent(entityId)}/features`,
  )
}

export function useFeatureCatalog(knowledgeBaseId: string | null) {
  return useQuery({
    queryKey: featureCatalogQueryKey(knowledgeBaseId),
    queryFn: () => getFeatureCatalog(knowledgeBaseId ?? ''),
    enabled: Boolean(knowledgeBaseId),
  })
}

export function useEntityFeatureValues(
  knowledgeBaseId: string | null,
  entityType: string | null,
  entityId: string | null,
) {
  return useQuery({
    queryKey: entityFeatureValuesQueryKey(knowledgeBaseId, entityType, entityId),
    queryFn: () => getEntityFeatureValues(
      knowledgeBaseId ?? '',
      entityType ?? '',
      entityId ?? '',
    ),
    enabled: Boolean(knowledgeBaseId && entityType && entityId),
  })
}
