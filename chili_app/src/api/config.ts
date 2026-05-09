import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { DomainConfig } from './contracts'

export const domainConfigQueryKey = ['domain-config'] as const

export function getDomainConfig(): Promise<DomainConfig> {
  return apiFetch<DomainConfig>('/config/domain')
}

export function useDomainConfig() {
  return useQuery({
    queryKey: domainConfigQueryKey,
    queryFn: getDomainConfig,
  })
}