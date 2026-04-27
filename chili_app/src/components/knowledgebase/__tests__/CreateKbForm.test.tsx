import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CreateKbForm } from '../CreateKbForm'

function createWrapper(): {
  Wrapper: ({ children }: { children: ReactNode }) => React.ReactElement
  client: QueryClient
} {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }): React.ReactElement {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )
  }
  return { Wrapper, client }
}

describe('CreateKbForm', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          id: 'kb-new',
          name: 'Bravo',
          description: '',
          entity_count: 0,
          relationship_count: 0,
          document_count: 0,
          status: 'active',
          created_at: '2026-04-27T00:00:00Z',
        }),
        {
          status: 201,
          headers: { 'content-type': 'application/json' },
        },
      ),
    ) as typeof globalThis.fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('returns null when not open', () => {
    const { Wrapper } = createWrapper()
    const { container } = render(
      <Wrapper>
        <CreateKbForm open={false} onClose={() => undefined} />
      </Wrapper>,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('submits the form and calls onCreated/onClose on success', async () => {
    const onClose = vi.fn()
    const onCreated = vi.fn()
    const { Wrapper } = createWrapper()
    render(
      <Wrapper>
        <CreateKbForm
          open
          onClose={onClose}
          onCreated={onCreated}
        />
      </Wrapper>,
    )
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Bravo' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create/i }))
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('kb-new'))
    expect(onClose).toHaveBeenCalled()
  })
})
