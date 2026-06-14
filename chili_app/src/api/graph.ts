import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { GraphEntityDetailResponse } from './contracts'

// TODO(future-development): the routed workbench currently uses /investigation
// graph queries; wire this detail route when a global entity drawer needs it.
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
