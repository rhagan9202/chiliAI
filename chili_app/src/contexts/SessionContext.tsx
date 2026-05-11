import React, { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { ApiError, apiRequest } from '../lib/apiClient'
import { SessionContext, type SessionStatus, type SessionUser } from './sessionContextValue'

export function SessionProvider({ children }: { children: ReactNode }): React.ReactElement {
  const [status, setStatus] = useState<SessionStatus>('loading')
  const [user, setUser] = useState<SessionUser | null>(null)

  useEffect(() => {
    let cancelled = false
    apiRequest<SessionUser>('/auth/me')
      .then((value) => {
        if (cancelled) return
        setUser(value)
        setStatus('authenticated')
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setStatus('unauthenticated')
        setUser(null)
        if (error instanceof ApiError && error.status !== 401) {
          // Non-401 errors during boot are surprising; log them.
          console.warn('SessionContext: /auth/me failed', error)
        }
      })
    return (): void => {
      cancelled = true
    }
  }, [])

  const signOut = async (): Promise<void> => {
    try {
      await apiRequest<unknown>('/auth/logout', { method: 'POST' })
    } finally {
      window.location.assign('/login')
    }
  }

  return (
    <SessionContext.Provider value={{ status, user, signOut }}>
      {children}
    </SessionContext.Provider>
  )
}
