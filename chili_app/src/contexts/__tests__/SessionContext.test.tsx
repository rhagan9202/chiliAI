import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SessionProvider, useSession } from '../SessionContext'

function Probe(): React.ReactElement {
  const session = useSession()
  return (
    <div>
      <div data-testid="status">{session.status}</div>
      <div data-testid="user">{session.user ? session.user.user_id : 'none'}</div>
    </div>
  )
}

describe('SessionContext', () => {
  let originalFetch: typeof fetch

  beforeEach(() => {
    originalFetch = globalThis.fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('starts in loading and resolves to authenticated when /auth/me returns a user', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({ user_id: 'u-1', roles: ['analyst'], email: 'u@e.com' }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      ),
    ) as unknown as typeof fetch

    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    expect(screen.getByTestId('status').textContent).toBe('loading')
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('authenticated')
    })
    expect(screen.getByTestId('user').textContent).toBe('u-1')
  })

  it('resolves to unauthenticated on 401', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'unauth' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('unauthenticated')
    })
  })
})
