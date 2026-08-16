import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CreateKnowledgeBasePanel } from '../CreateKnowledgeBasePanel'

const originalFetch = globalThis.fetch

let lastRequestBody: unknown = null

beforeEach(() => {
  lastRequestBody = null
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.endsWith('/knowledgebases') && init?.method === 'POST') {
      lastRequestBody = init.body ? JSON.parse(init.body as string) : null
      return new Response(
        JSON.stringify({
          id: 'kb-new',
          name: 'New corpus',
          description: 'New source material',
          status: 'building',
          document_count: 0,
          entity_count: 0,
          relationship_count: 0,
          created_at: '2026-08-16T00:00:00Z',
        }),
        { status: 201, headers: { 'content-type': 'application/json' } },
      )
    }
    throw new Error(`unexpected request: ${url}`)
  }) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

function renderPanel(onCreated = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  const result = render(<CreateKnowledgeBasePanel onCreated={onCreated} />, { wrapper: Wrapper })
  return { onCreated, container: result.container }
}

describe('CreateKnowledgeBasePanel', () => {
  it('reads as a New knowledge base affordance, not a permanent form', () => {
    const { container } = renderPanel()

    const details = container.querySelector('details')
    expect(details).not.toBeNull()
    expect(details).not.toHaveAttribute('open')
    expect(screen.getByText('New knowledge base').tagName).toBe('SUMMARY')
  })

  it('disables submit until a name is entered', () => {
    renderPanel()

    fireEvent.click(screen.getByText('New knowledge base'))

    expect(screen.getByRole('button', { name: 'Create knowledge base' })).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/knowledge base name/i), {
      target: { value: 'New corpus' },
    })

    expect(screen.getByRole('button', { name: 'Create knowledge base' })).toBeEnabled()
  })

  it('creates the knowledge base and reports its id', async () => {
    const { onCreated } = renderPanel()

    fireEvent.click(screen.getByText('New knowledge base'))
    fireEvent.change(screen.getByLabelText(/knowledge base name/i), {
      target: { value: 'New corpus' },
    })
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'New source material' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create knowledge base' }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('kb-new'))
    expect(lastRequestBody).toEqual({ name: 'New corpus', description: 'New source material' })
  })

  it('trims padded whitespace from the name and description before submitting', async () => {
    const { onCreated } = renderPanel()

    fireEvent.click(screen.getByText('New knowledge base'))
    fireEvent.change(screen.getByLabelText(/knowledge base name/i), {
      target: { value: '  New corpus  ' },
    })
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: '  New source material  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create knowledge base' }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('kb-new'))
    expect(lastRequestBody).toEqual({ name: 'New corpus', description: 'New source material' })
  })

  it('clears the fields after a successful create', async () => {
    renderPanel()

    fireEvent.click(screen.getByText('New knowledge base'))
    fireEvent.change(screen.getByLabelText(/knowledge base name/i), {
      target: { value: 'New corpus' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create knowledge base' }))

    await waitFor(() =>
      expect(screen.getByLabelText(/knowledge base name/i)).toHaveValue(''),
    )
  })
})
