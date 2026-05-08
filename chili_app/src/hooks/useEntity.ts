import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'

import { apiRequest } from '../lib/apiClient'
import type { Entity, EntityDetailResponse } from '../types/api'

export function entityQueryKey(
  kbId: string | null,
  entityId: string | null,
): readonly unknown[] {
  return ['investigation', 'entity', kbId, entityId] as const
}

export function useEntity(
  entityId: string | null,
  kbId: string | null,
): UseQueryResult<Entity, Error> {
  return useQuery<Entity, Error>({
    queryKey: entityQueryKey(kbId, entityId),
    queryFn: async () => {
      const response = await apiRequest<EntityDetailResponse>(
        `/investigation/entities/${encodeURIComponent(entityId ?? '')}?kb_id=${encodeURIComponent(kbId ?? '')}`,
      )
      return response.entity
    },
    enabled: Boolean(entityId) && Boolean(kbId),
  })
}
