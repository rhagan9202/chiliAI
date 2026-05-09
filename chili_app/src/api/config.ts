import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { DomainConfig, DomainConfigSchema, DomainFeatures } from './contracts'

export const domainConfigQueryKey = ['domain-config'] as const
export const domainFeaturesQueryKey = ['domain-features'] as const
export const domainConfigSchemaQueryKey = ['domain-config-schema'] as const

export function getDomainConfig(): Promise<DomainConfig> {
  return apiFetch<DomainConfig>('/config/domain')
}

export function getDomainFeatures(): Promise<DomainFeatures> {
  return apiFetch<DomainFeatures>('/config/features')
}

export function getDomainConfigSchema(): Promise<DomainConfigSchema> {
  return apiFetch<DomainConfigSchema>('/config/domain/schema')
}

export function useDomainConfig() {
  return useQuery({
    queryKey: domainConfigQueryKey,
    queryFn: getDomainConfig,
  })
}

export function useDomainFeatures() {
  return useQuery({
    queryKey: domainFeaturesQueryKey,
    queryFn: getDomainFeatures,
  })
}

export function useDomainConfigSchema() {
  return useQuery({
    queryKey: domainConfigSchemaQueryKey,
    queryFn: getDomainConfigSchema,
  })
}