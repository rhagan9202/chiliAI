import { useCallback, useEffect, useState } from 'react'

import { ApiError, apiRequest } from '../lib/apiClient'
import type { DomainConfig } from '../types/domainConfig'

// Note: the project intentionally does not depend on a YAML serializer
// (no `js-yaml` / `yaml` package). The backend currently exposes domain
// config as JSON via `GET /config/domain`, so this hook returns a
// pretty-printed JSON representation. The CodeMirror surface still
// applies the YAML language extension for visual familiarity — this is
// documented as a deliberate deviation in SP_E9_S09.

export interface DomainConfigYamlState {
  text: string
  config: DomainConfig | null
  loading: boolean
  error: Error | null
  reload: () => Promise<void>
}

export function serializeConfig(config: DomainConfig): string {
  return JSON.stringify(config, null, 2)
}

export function useDomainConfigYaml(): DomainConfigYamlState {
  const [text, setText] = useState<string>('')
  const [config, setConfig] = useState<DomainConfig | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<Error | null>(null)

  const reload = useCallback(async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const value = await apiRequest<DomainConfig>('/config/domain')
      setConfig(value)
      setText(serializeConfig(value))
    } catch (err: unknown) {
      const wrapped =
        err instanceof ApiError || err instanceof Error
          ? err
          : new Error(String(err))
      setError(wrapped)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  return { text, config, loading, error, reload }
}
