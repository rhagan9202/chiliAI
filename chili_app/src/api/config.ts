import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type {
  ApplyPackRequest,
  ConfigSwapResponse,
  DomainConfig,
  DomainConfigSchema,
  DomainFeatures,
  PackListResponse,
  SwitchPackRequest,
  ValidatePackRequest,
  ValidatePackResponse,
} from './contracts'

export const domainConfigQueryKey = ['domain-config'] as const
export const domainFeaturesQueryKey = ['domain-features'] as const
export const domainConfigSchemaQueryKey = ['domain-config-schema'] as const
export const configPacksQueryKey = ['config-packs'] as const

/**
 * Query keys that must be refetched after a successful pack apply/switch so
 * nav, labels, and the entity registry re-render in place (hot swap, no
 * reload). Mirrors the domain-config defaults block in app/providers.tsx.
 */
export const domainConfigInvalidationKeys = [
  domainConfigQueryKey,
  domainFeaturesQueryKey,
  domainConfigSchemaQueryKey,
] as const

export function getDomainConfig(): Promise<DomainConfig> {
  return apiFetch<DomainConfig>('/config/domain')
}

export function getDomainFeatures(): Promise<DomainFeatures> {
  return apiFetch<DomainFeatures>('/config/features')
}

export function getDomainConfigSchema(): Promise<DomainConfigSchema> {
  return apiFetch<DomainConfigSchema>('/config/domain/schema')
}

export function getConfigPacks(): Promise<PackListResponse> {
  return apiFetch<PackListResponse>('/config/packs')
}

export function validatePack(payload: ValidatePackRequest): Promise<ValidatePackResponse> {
  return apiPost<ValidatePackResponse, ValidatePackRequest>('/config/validate', payload)
}

export function applyPack(payload: ApplyPackRequest): Promise<ConfigSwapResponse> {
  return apiPost<ConfigSwapResponse, ApplyPackRequest>('/config/apply', payload)
}

export function switchPack(payload: SwitchPackRequest): Promise<ConfigSwapResponse> {
  return apiPost<ConfigSwapResponse, SwitchPackRequest>('/config/switch', payload)
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

export function useConfigPacks(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: configPacksQueryKey,
    queryFn: getConfigPacks,
    enabled: options.enabled ?? true,
  })
}

export function useValidatePack() {
  return useMutation({
    mutationFn: validatePack,
  })
}

function useSwapInvalidation() {
  const queryClient = useQueryClient()
  return () => {
    for (const queryKey of domainConfigInvalidationKeys) {
      void queryClient.invalidateQueries({ queryKey })
    }
    void queryClient.invalidateQueries({ queryKey: configPacksQueryKey })
  }
}

export function useApplyPack() {
  const invalidateAfterSwap = useSwapInvalidation()
  return useMutation({
    mutationFn: applyPack,
    onSuccess: invalidateAfterSwap,
  })
}

export function useSwitchPack() {
  const invalidateAfterSwap = useSwapInvalidation()
  return useMutation({
    mutationFn: switchPack,
    onSuccess: invalidateAfterSwap,
  })
}
