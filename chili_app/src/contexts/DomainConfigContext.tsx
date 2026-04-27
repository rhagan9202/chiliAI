import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { LoadingSpinner } from '../components/common/LoadingSpinner'
import { apiRequest } from '../lib/apiClient'
import type { DomainConfig } from '../types/domainConfig'
import { DomainConfigContext } from './domainConfigContextValue'

export interface DomainConfigProviderProps {
  children: ReactNode
}

export function DomainConfigProvider({
  children,
}: DomainConfigProviderProps): React.ReactElement {
  const [config, setConfig] = useState<DomainConfig | null>(null)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    let cancelled = false
    apiRequest<DomainConfig>('/config/domain')
      .then((value) => {
        if (!cancelled) setConfig(value)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err : new Error(String(err)))
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (error) {
    return (
      <div
        role="alert"
        style={{
          padding: 24,
          margin: 24,
          border: '1px solid #e5e4e7',
          borderRadius: 8,
          background: 'rgba(239, 68, 68, 0.05)',
        }}
      >
        <h2 style={{ marginTop: 0 }}>Failed to load domain configuration</h2>
        <p>{error.message}</p>
        <p style={{ fontSize: 14 }}>
          Verify the API is running at the configured base URL and that{' '}
          <code>GET /config/domain</code> is reachable.
        </p>
      </div>
    )
  }

  if (!config) {
    return <LoadingSpinner label="Loading domain configuration…" />
  }

  return (
    <DomainConfigContext.Provider value={{ config }}>
      {children}
    </DomainConfigContext.Provider>
  )
}
