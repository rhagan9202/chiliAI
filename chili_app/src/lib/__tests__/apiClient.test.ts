import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiRequest } from '../apiClient'

describe('apiClient', () => {
  let originalFetch: typeof fetch
  let assignMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    originalFetch = globalThis.fetch

    // jsdom's window.location.assign is non-configurable; replace the entire
    // location object with a plain stub so we can spy on assign.
    assignMock = vi.fn()
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (window as any).location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { assign: assignMock },
    })
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('includes credentials on every request', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    globalThis.fetch = fetchMock as unknown as typeof fetch

    await apiRequest<{ ok: boolean }>('/anything')

    expect(fetchMock).toHaveBeenCalled()
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.credentials).toBe('include')
  })

  it('redirects to /login when the API returns 401', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'expired' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    await expect(apiRequest('/protected')).rejects.toBeInstanceOf(ApiError)
    expect(assignMock).toHaveBeenCalledWith('/login')
  })

  it('does not redirect for non-401 errors', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'bad' }), {
        status: 400,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    await expect(apiRequest('/anything')).rejects.toBeInstanceOf(ApiError)
    expect(assignMock).not.toHaveBeenCalled()
  })

  it('does not redirect for 401 from /auth/* endpoints', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'unauth' }), {
        status: 401,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    await expect(apiRequest('/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(assignMock).not.toHaveBeenCalled()
  })
})
