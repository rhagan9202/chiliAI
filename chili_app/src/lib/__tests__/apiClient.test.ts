import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL, ApiError, apiErrorMessage, apiRequest } from '../apiClient'

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
    vi.useRealTimers()
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

    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('defaults API requests to the same-origin /api prefix', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    globalThis.fetch = fetchMock as unknown as typeof fetch

    await apiRequest<{ ok: boolean }>('/anything')

    expect(API_BASE_URL).toBe('/api')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/anything',
      expect.objectContaining({ credentials: 'include' }),
    )
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

  it('formats FastAPI validation details into readable messages', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          detail: [
            { loc: ['body', 'rows', 0, 'claim_id'], msg: 'Field required' },
            { loc: ['body', 'rows', 0, 'amount'], msg: 'Input should be a number' },
          ],
        }),
        {
          status: 422,
          headers: { 'content-type': 'application/json' },
        },
      ),
    ) as unknown as typeof fetch

    await expect(apiRequest('/records/kb-1/push')).rejects.toMatchObject({
      message: 'body.rows.0.claim_id: Field required\nbody.rows.0.amount: Input should be a number',
    })
  })

  it('extracts structured ApiError messages for UI callers', () => {
    const error = new ApiError(422, 'fallback', {
      detail: [{ loc: ['body', 'file'], msg: 'Unsupported media type' }],
    })

    expect(apiErrorMessage(error, 'Upload failed.')).toBe(
      'body.file: Unsupported media type',
    )
  })

  it('times out requests with a user-readable error', async () => {
    vi.useFakeTimers()
    globalThis.fetch = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        }),
    ) as unknown as typeof fetch

    const request = apiRequest('/slow', { timeoutMs: 50 })
    const assertion = expect(request).rejects.toMatchObject({
      status: 0,
      message: 'Request timed out. Please try again.',
    })
    await vi.advanceTimersByTimeAsync(50)

    await assertion
  })

  it('preserves caller-provided abort signals', async () => {
    const controller = new AbortController()
    globalThis.fetch = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        }),
    ) as unknown as typeof fetch

    const request = apiRequest('/abortable', {
      signal: controller.signal,
      timeoutMs: 0,
    })
    controller.abort()

    await expect(request).rejects.toMatchObject({ name: 'AbortError' })
  })
})
