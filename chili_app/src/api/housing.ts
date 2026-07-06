import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { HousingInstallationsResponse, HousingOverviewResponse } from './contracts'

export type HousingPeriodFilters = {
  periodStart?: string
  periodEnd?: string
}

export const housingOverviewQueryKey = (filters: HousingPeriodFilters | null = null) =>
  ['housing', 'overview', filters] as const
export const housingInstallationsQueryKey = (filters: HousingPeriodFilters | null = null) =>
  ['housing', 'installations', filters] as const

function housingPeriodQuery(filters?: HousingPeriodFilters): string {
  const params = new URLSearchParams()
  if (filters?.periodStart !== undefined) params.set('period_start', filters.periodStart)
  if (filters?.periodEnd !== undefined) params.set('period_end', filters.periodEnd)
  return params.toString()
}

function withOptionalQuery(path: string, query: string): string {
  return query ? `${path}?${query}` : path
}

export function getHousingOverview(
  filters?: HousingPeriodFilters,
): Promise<HousingOverviewResponse> {
  return apiFetch<HousingOverviewResponse>(
    withOptionalQuery('/housing/overview', housingPeriodQuery(filters)),
  )
}

export function getHousingInstallations(
  filters?: HousingPeriodFilters,
): Promise<HousingInstallationsResponse> {
  return apiFetch<HousingInstallationsResponse>(
    withOptionalQuery('/housing/installations', housingPeriodQuery(filters)),
  )
}

export function useHousingOverview(filters: HousingPeriodFilters | null = null) {
  return useQuery({
    queryKey: housingOverviewQueryKey(filters),
    queryFn: () => getHousingOverview(filters ?? undefined),
  })
}

export function useHousingInstallations(filters: HousingPeriodFilters | null = null) {
  return useQuery({
    queryKey: housingInstallationsQueryKey(filters),
    queryFn: () => getHousingInstallations(filters ?? undefined),
  })
}
