// Lightweight typed fetch wrapper. Base URL comes from VITE_API_BASE_URL.

const DEFAULT_BASE_URL = 'http://localhost:8000'

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
  if (options.body !== undefined) {
    if (
      options.body instanceof FormData ||
      options.body instanceof Blob ||
      typeof options.body === 'string'
    ) {
      body = options.body as BodyInit
    } else {
      headers['Content-Type'] = headers['Content-Type'] ?? 'application/json'
      body = JSON.stringify(options.body)
    }
  }

  const response = await fetch(url, {
    method: options.method ?? 'GET',
    headers,
    body,
    signal: options.signal,
  })

  const parsed = await parseBody(response)

  if (!response.ok) {
    const message =
      parsed && typeof parsed === 'object' && 'detail' in parsed
        ? String((parsed as { detail: unknown }).detail)
        : `Request failed with status ${response.status}`
    throw new ApiError(response.status, message, parsed)
  }

  return parsed as T
}
