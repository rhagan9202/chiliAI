import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { HousingInstallationsResponse } from './contracts'

export type HousingPeriodFilters = {
  periodStart?: string
  periodEnd?: string
}

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

// The GET /housing/overview endpoint stays live (backend router tests pin it
// as the aggregate semantic contract), but the dashboard recomputes every
// portfolio aggregate client-side from the installation rows
// (housingFilters.aggregateInstallations) so the summary band can follow the
// filters — no frontend binding for the overview endpoint remains.

export function getHousingInstallations(
  filters?: HousingPeriodFilters,
): Promise<HousingInstallationsResponse> {
  return apiFetch<HousingInstallationsResponse>(
    withOptionalQuery('/housing/installations', housingPeriodQuery(filters)),
  )
}

export function useHousingInstallations(filters: HousingPeriodFilters | null = null) {
  return useQuery({
    queryKey: housingInstallationsQueryKey(filters),
    queryFn: () => getHousingInstallations(filters ?? undefined),
  })
}
