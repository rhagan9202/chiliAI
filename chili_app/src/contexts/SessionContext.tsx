import React, { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { ApiError, apiRequest } from '../lib/apiClient'

export interface SessionUser {
  user_id: string
  roles: string[]
  email: string | null
}

export type SessionStatus = 'loading' | 'authenticated' | 'unauthenticated'

export interface SessionState {
  status: SessionStatus
  user: SessionUser | null
  signOut: () => Promise<void>
}

const SessionContext = createContext<SessionState | undefined>(undefined)

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
        // Any failure (401, network, etc.) → unauthenticated
        setStatus('unauthenticated')
        setUser(null)
        if (error instanceof ApiError && error.status !== 401) {
          // Non-401 errors during boot are surprising; log them.
          // eslint-disable-next-line no-console
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

export function useSession(): SessionState {
  const ctx = useContext(SessionContext)
  if (ctx === undefined) {
    throw new Error('useSession must be used within a SessionProvider.')
  }
  return ctx
}
