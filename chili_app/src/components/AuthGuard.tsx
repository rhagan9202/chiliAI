import { Navigate } from 'react-router-dom'

import { useSession } from '../contexts/SessionContext'

export function AuthGuard({ children }: { children: React.ReactNode }): React.ReactElement {
  const { status } = useSession()

  if (status === 'loading') {
    return (
      <div className="auth-loading" role="status">
        Loading…
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

export default AuthGuard
