import { keepPreviousData, useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'

import { apiRequest } from '../lib/apiClient'
import type { NeighborhoodResponse, SubgraphResult } from '../types/api'

export interface NeighborhoodData {
  centerEntityId: string
  subgraph: SubgraphResult
}

export function neighborhoodQueryKey(
  kbId: string | null,
  entityId: string | null,
  depth: number,
): readonly unknown[] {
  return ['investigation', 'neighborhood', kbId, entityId, depth] as const
}

export function useNeighborhood(
  entityId: string | null,
  kbId: string | null,
  depth = 2,
): UseQueryResult<NeighborhoodData, Error> {
  return useQuery<NeighborhoodData, Error>({
    queryKey: neighborhoodQueryKey(kbId, entityId, depth),
    queryFn: async () => {
      const response = await apiRequest<NeighborhoodResponse>(
        `/investigation/entities/${encodeURIComponent(entityId ?? '')}/neighborhood?kb_id=${encodeURIComponent(kbId ?? '')}&depth=${depth}`,
      )
      return {
        centerEntityId: response.center_entity_id,
        subgraph: {
          nodes: response.entities,
          edges: response.relationships,
        },
      }
    },
    enabled: Boolean(entityId) && Boolean(kbId),
    placeholderData: keepPreviousData,
  })
}
