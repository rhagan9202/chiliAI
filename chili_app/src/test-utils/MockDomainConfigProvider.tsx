import type { ReactNode } from 'react'

import { DomainConfigContext } from '../contexts/domainConfigContextValue'
import type { DomainConfig } from '../types/domainConfig'

const defaultMockConfig: DomainConfig = {
  schema_version: '1.0',
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
  ingestion: {
    sources: [],
    chunking: {
      strategy: 'recursive',
      chunk_size: 1000,
      chunk_overlap: 200,
      min_chunk_size: 50,
    },
  },
  alerts: { thresholds: {} },
}

export interface MockDomainConfigProviderProps {
  children: ReactNode
  config?: Partial<DomainConfig>
}

export function MockDomainConfigProvider({
  children,
  config,
}: MockDomainConfigProviderProps): React.ReactElement {
  const merged: DomainConfig = { ...defaultMockConfig, ...config }
  return (
    <DomainConfigContext.Provider value={{ config: merged }}>
      {children}
    </DomainConfigContext.Provider>
  )
}
