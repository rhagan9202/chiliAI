import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type {
  CapabilityListResponse,
  CapabilitySideEffectClass,
} from './contracts'

export interface CapabilityRegistryFilters {
  role?: string
  module?: string
  sideEffectClass?: CapabilitySideEffectClass
  limit?: number
  offset?: number
}

export function capabilityRegistryQueryKey(
  knowledgeBaseId: string | null,
  filters: CapabilityRegistryFilters = {},
) {
  return ['capabilities', knowledgeBaseId ?? 'missing', filters] as const
}

export function listCapabilities(
  knowledgeBaseId: string,
  filters: CapabilityRegistryFilters = {},
): Promise<CapabilityListResponse> {
  const params = new URLSearchParams()
  if (filters.role !== undefined) {
    params.set('role', filters.role)
  }
  if (filters.module !== undefined) {
    params.set('module', filters.module)
  }
  if (filters.sideEffectClass !== undefined) {
    params.set('side_effect_class', filters.sideEffectClass)
  }
  params.set('limit', String(filters.limit ?? 100))
  params.set('offset', String(filters.offset ?? 0))
  return apiFetch<CapabilityListResponse>(
    `/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/capabilities?${params}`,
  )
}

export function useCapabilityRegistry(
  knowledgeBaseId: string | null,
  filters: CapabilityRegistryFilters = {},
) {
  return useQuery({
    queryKey: capabilityRegistryQueryKey(knowledgeBaseId, filters),
    queryFn: () => listCapabilities(knowledgeBaseId ?? '', filters),
    enabled: Boolean(knowledgeBaseId),
  })
}
