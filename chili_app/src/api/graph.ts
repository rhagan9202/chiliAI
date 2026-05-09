import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { GraphEntityDetailResponse } from './contracts'

export function graphEntityQueryKey(entityId: string) {
  return ['graph', 'entity', entityId] as const
}

export function getGraphEntity(entityId: string): Promise<GraphEntityDetailResponse> {
  return apiFetch<GraphEntityDetailResponse>(`/graph/entities/${entityId}`)
}

export function useGraphEntity(entityId: string | null) {
  return useQuery({
    queryKey: graphEntityQueryKey(entityId ?? 'missing'),
    queryFn: () => getGraphEntity(entityId ?? ''),
    enabled: Boolean(entityId),
  })
}