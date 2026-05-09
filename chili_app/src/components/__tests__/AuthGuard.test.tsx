import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthGuard } from '../AuthGuard'
import { SessionProvider } from '../../contexts/SessionContext'

function Protected(): React.ReactElement {
  return <div data-testid="protected">protected content</div>
}

function LoginPage(): React.ReactElement {
  return <div data-testid="login">login page</div>
}

function withRouter(initial: string, fetchImpl: typeof fetch): React.ReactElement {
  globalThis.fetch = fetchImpl
  return (
    <MemoryRouter initialEntries={[initial]}>
      <SessionProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <AuthGuard>
                <Protected />
              </AuthGuard>
            }
          />
        </Routes>
      </SessionProvider>
    </MemoryRouter>
  )
}

describe('AuthGuard', () => {
  let originalFetch: typeof fetch

  beforeEach(() => {
    originalFetch = globalThis.fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('renders children when authenticated', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ user_id: 'u', roles: [], email: null }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    render(withRouter('/', fetchMock))

    await waitFor(() => {
      expect(screen.getByTestId('protected')).toBeInTheDocument()
    })
  })

  it('navigates to /login when unauthenticated', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'no' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    render(withRouter('/', fetchMock))

    await waitFor(() => {
      expect(screen.getByTestId('login')).toBeInTheDocument()
    })
  })
})
