import { API_BASE_URL, apiRequest } from '../lib/apiClient'

export { API_BASE_URL }

export async function apiFetch<TResponse>(
  path: string,
  init: RequestInit = {},
): Promise<TResponse> {
  return apiRequest<TResponse>(path, {
    method: (init.method as 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH' | undefined) ?? 'GET',
    body: init.body as unknown,
    headers: (init.headers as Record<string, string> | undefined) ?? undefined,
    signal: init.signal ?? undefined,
  })
}

export function apiPost<TResponse, TBody>(path: string, body: TBody): Promise<TResponse> {
  return apiRequest<TResponse>(path, { method: 'POST', body })
}

export function apiPatch<TResponse, TBody>(path: string, body: TBody): Promise<TResponse> {
  return apiRequest<TResponse>(path, { method: 'PATCH', body })
}

export function apiDelete<TResponse>(path: string): Promise<TResponse> {
  return apiRequest<TResponse>(path, { method: 'DELETE' })
}

export function apiUpload<TResponse>(path: string, formData: FormData): Promise<TResponse> {
  return apiRequest<TResponse>(path, { method: 'POST', body: formData })
}
