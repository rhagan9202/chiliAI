import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { domainConfigQueryKey } from '../api/config'
import type { DomainConfig } from '../api/contracts'

const defaultMockConfig: DomainConfig = {
  domain: {
    name: 'mock',
    display_name: 'Mock Domain',
    description: 'Test fixture domain configuration',
  },
  entities: [],
  relationships: [],
  capabilities: {
    timeseries: false,
    gnn: false,
    risk_scoring: false,
    rag_chat: false,
    explainability: false,
  },
  ingestion: {},
  alerts: { thresholds: {} },
}

export interface MockDomainConfigProviderProps {
  children: ReactNode
  config?: Partial<DomainConfig>
}

/**
 * Test utility that seeds the React Query cache with a mock domain config so
 * consumers of `useDomainConfig()` from `api/config` get a resolved value
 * without making a real network request.
 */
export function MockDomainConfigProvider({
  children,
  config,
}: MockDomainConfigProviderProps): React.ReactElement {
  const merged: DomainConfig = { ...defaultMockConfig, ...config }

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  queryClient.setQueryData(domainConfigQueryKey, merged)

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}
