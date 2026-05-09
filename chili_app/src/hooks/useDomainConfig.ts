import { useDomainConfigContext } from '../contexts/domainConfigContextValue'
import type { DomainConfig } from '../types/domainConfig'

export function useDomainConfig(): DomainConfig {
  const { config } = useDomainConfigContext()
  return config
}
