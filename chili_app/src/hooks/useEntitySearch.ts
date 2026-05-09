import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'

import { apiRequest } from '../lib/apiClient'
import type { EntitySearchResponse } from '../types/api'

export function entitySearchQueryKey(
  kbId: string | null,
  query: string,
  limit: number,
): readonly unknown[] {
  return ['investigation', 'entity-search', kbId, query, limit] as const
}

export function useEntitySearch(
  kbId: string | null,
  query: string,
  limit = 20,
): UseQueryResult<EntitySearchResponse, Error> {
  const normalizedQuery = query.trim()
  return useQuery<EntitySearchResponse, Error>({
    queryKey: entitySearchQueryKey(kbId, normalizedQuery, limit),
    queryFn: () =>
      apiRequest<EntitySearchResponse>(
        `/investigation/search?kb_id=${encodeURIComponent(kbId ?? '')}&q=${encodeURIComponent(normalizedQuery)}&limit=${limit}`,
      ),
    enabled: Boolean(kbId) && normalizedQuery.length > 0,
  })
}
