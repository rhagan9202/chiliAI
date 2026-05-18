// Lightweight typed fetch wrapper. Base URL comes from VITE_API_BASE_URL.

const DEFAULT_BASE_URL = '/api'
const DEFAULT_TIMEOUT_MS = 30_000

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? DEFAULT_BASE_URL

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(status: number, message: string, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
  timeoutMs?: number
}

function validationMessageFromDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item) => {
      if (typeof item === 'string') {
        return [item]
      }
      if (item && typeof item === 'object') {
        const record = item as Record<string, unknown>
        const message = record.msg ?? record.message ?? record.detail
        if (typeof message !== 'string') {
          return []
        }
        const location = Array.isArray(record.loc)
          ? record.loc.map(String).join('.')
          : null
        return [location ? `${location}: ${message}` : message]
      }
      return []
    })

    return messages.length > 0 ? messages.join('\n') : null
  }

  if (detail && typeof detail === 'object') {
    const record = detail as Record<string, unknown>
    const message = record.msg ?? record.message ?? record.detail
    return typeof message === 'string' ? message : null
  }

  return null
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const body = error.body
    if (body && typeof body === 'object' && 'detail' in body) {
      return validationMessageFromDetail((body as { detail: unknown }).detail) ?? error.message
    }
    return error.message
  }

  if (error instanceof Error) {
    return error.message
  }

  return fallback
}

async function parseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    try {
      return (await response.json()) as unknown
    } catch {
      return null
    }
  }
  const text = await response.text()
  return text.length > 0 ? text : null
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const url = path.startsWith('http')
    ? path
    : `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.headers ?? {}),
  }

  let body: BodyInit | undefined
  let isFormDataBody = false
  if (options.body !== undefined) {
    if (
      options.body instanceof FormData ||
      options.body instanceof Blob ||
      typeof options.body === 'string'
    ) {
      isFormDataBody = options.body instanceof FormData
      body = options.body as BodyInit
    } else {
      headers['Content-Type'] = headers['Content-Type'] ?? 'application/json'
      body = JSON.stringify(options.body)
    }
  }

  const timeoutMs = options.timeoutMs ?? (isFormDataBody ? 0 : DEFAULT_TIMEOUT_MS)
  const controller = new AbortController()
  let timedOut = false
  const timeout = timeoutMs > 0
    ? window.setTimeout(() => {
        timedOut = true
        controller.abort()
      }, timeoutMs)
    : null
  const abortFromCaller = () => controller.abort(options.signal?.reason)
  if (options.signal?.aborted) {
    abortFromCaller()
  } else {
    options.signal?.addEventListener('abort', abortFromCaller, { once: true })
  }

  let response: Response
  try {
    response = await fetch(url, {
      method: options.method ?? 'GET',
      headers,
      body,
      credentials: 'include',
      signal: controller.signal,
    })
  } catch (error) {
    if (timedOut) {
      throw new ApiError(0, 'Request timed out. Please try again.', {
        detail: 'Request timed out. Please try again.',
      })
    }
    throw error
  } finally {
    if (timeout !== null) {
      window.clearTimeout(timeout)
    }
    options.signal?.removeEventListener('abort', abortFromCaller)
  }

  const parsed = await parseBody(response)

  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) {
      if (typeof window !== 'undefined') {
        window.location.assign('/login')
      }
    }
    const message =
      parsed && typeof parsed === 'object' && 'detail' in parsed
        ? validationMessageFromDetail((parsed as { detail: unknown }).detail)
          ?? `Request failed with status ${response.status}`
        : `Request failed with status ${response.status}`
    throw new ApiError(response.status, message, parsed)
  }

  return parsed as T
}
