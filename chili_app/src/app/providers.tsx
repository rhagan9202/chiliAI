import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import type { PropsWithChildren } from 'react'
import { useState } from 'react'

import {
  domainConfigQueryKey,
  domainConfigSchemaQueryKey,
  domainFeaturesQueryKey,
} from '../api/config'
import { SessionProvider } from '../contexts/SessionContext'

const MUTABLE_DATA_STALE_TIME_MS = 30_000
const DOMAIN_CONFIG_STALE_TIME_MS = 10 * 60_000

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(() => {
    const client = new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
            staleTime: MUTABLE_DATA_STALE_TIME_MS,
          },
        },
      })

    ;[
      domainConfigQueryKey,
      domainFeaturesQueryKey,
      domainConfigSchemaQueryKey,
    ].forEach((queryKey) => {
      client.setQueryDefaults(queryKey, {
        staleTime: DOMAIN_CONFIG_STALE_TIME_MS,
      })
    })

    return client
  })

  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>{children}</SessionProvider>
      {import.meta.env.DEV ? <ReactQueryDevtools initialIsOpen={false} /> : null}
    </QueryClientProvider>
  )
}
