import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  API_BASE_URL,
  ApiError,
  apiErrorMessage,
  apiRequest,
  apiUploadWithProgress,
} from '../apiClient'

/**
 * Minimal XMLHttpRequest stub for jsdom. jsdom does not perform real uploads,
 * so we drive lifecycle handlers manually to assert progress/error/abort paths.
 */
class FakeXhr {
  static last: FakeXhr | null = null
  method = ''
  url = ''
  withCredentials = false
  responseType = ''
  status = 0
  response: unknown = null
  responseText = ''
  sentBody: unknown = null
  readonly upload: { onprogress: ((event: ProgressEvent) => void) | null } = {
    onprogress: null,
  }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null

  constructor() {
    FakeXhr.last = this
  }

  open(method: string, url: string): void {
    this.method = method
    this.url = url
  }

  send(body: unknown): void {
    this.sentBody = body
  }

  emitProgress(loaded: number, total: number): void {
    this.upload.onprogress?.({
      lengthComputable: true,
      loaded,
      total,
    } as ProgressEvent)
  }
}

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

  it('does not apply the default timeout to FormData uploads', async () => {
    const setTimeoutSpy = vi.spyOn(window, 'setTimeout')
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    ) as unknown as typeof fetch

    const formData = new FormData()
    formData.append('files', new Blob(['{}'], { type: 'application/json' }), 'claims.json')

    await apiRequest('/upload', { method: 'POST', body: formData })

    expect(setTimeoutSpy).not.toHaveBeenCalled()
  })

  describe('apiUploadWithProgress', () => {
    let originalXhr: typeof XMLHttpRequest

    beforeEach(() => {
      originalXhr = globalThis.XMLHttpRequest
      FakeXhr.last = null
      globalThis.XMLHttpRequest = FakeXhr as unknown as typeof XMLHttpRequest
    })

    afterEach(() => {
      globalThis.XMLHttpRequest = originalXhr
    })

    it('POSTs form data with credentials to the prefixed url', async () => {
      const form = new FormData()
      form.append('file', new Blob(['a'], { type: 'text/csv' }), 'a.csv')
      const promise = apiUploadWithProgress<{ ok: boolean }>('/records/kb-1/files', form)

      const xhr = FakeXhr.last
      expect(xhr).not.toBeNull()
      expect(xhr?.method).toBe('POST')
      expect(xhr?.url).toBe('/api/records/kb-1/files')
      expect(xhr?.withCredentials).toBe(true)
      expect(xhr?.sentBody).toBe(form)

      xhr!.status = 200
      xhr!.response = { ok: true }
      xhr!.onload?.()

      await expect(promise).resolves.toEqual({ ok: true })
    })

    it('reports upload progress as a 0-100 percentage', async () => {
      const onUploadProgress = vi.fn()
      const form = new FormData()
      const promise = apiUploadWithProgress<{ ok: boolean }>('/upload', form, {
        onUploadProgress,
      })

      const xhr = FakeXhr.last!
      xhr.emitProgress(25, 100)
      xhr.emitProgress(100, 100)

      expect(onUploadProgress).toHaveBeenNthCalledWith(1, 25)
      expect(onUploadProgress).toHaveBeenNthCalledWith(2, 100)

      xhr.status = 200
      xhr.response = { ok: true }
      xhr.onload?.()
      await promise
    })

    it('rejects with an ApiError carrying the parsed detail on non-2xx', async () => {
      const form = new FormData()
      const promise = apiUploadWithProgress('/upload', form)

      const xhr = FakeXhr.last!
      xhr.status = 422
      xhr.response = { detail: 'Unsupported media type' }
      xhr.onload?.()

      await expect(promise).rejects.toMatchObject({
        status: 422,
        message: 'Unsupported media type',
      })
    })

    it('rejects with a network ApiError on transport failure', async () => {
      const form = new FormData()
      const promise = apiUploadWithProgress('/upload', form)

      FakeXhr.last!.onerror?.()

      await expect(promise).rejects.toMatchObject({ status: 0 })
    })
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
