import { createContext, useContext } from 'react'

import type { DomainConfig } from '../types/domainConfig'

export interface DomainConfigContextValue {
  config: DomainConfig
}

export const DomainConfigContext = createContext<DomainConfigContextValue | null>(
  null,
)

export function useDomainConfigContext(): DomainConfigContextValue {
  const ctx = useContext(DomainConfigContext)
  if (!ctx) {
    throw new Error(
      'useDomainConfigContext must be used inside a <DomainConfigProvider>',
    )
  }
  return ctx
}
