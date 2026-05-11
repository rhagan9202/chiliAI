import { createContext, useContext } from 'react'

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

export const SessionContext = createContext<SessionState | undefined>(undefined)

export function useSession(): SessionState {
  const ctx = useContext(SessionContext)
  if (ctx === undefined) {
    throw new Error('useSession must be used within a SessionProvider.')
  }
  return ctx
}
