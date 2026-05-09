import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

import { RagChat } from '../RagChat'
import { useChatStore } from '../../stores/chatStore'

interface MockKbResponse {
  items: Array<{
    id: string
    name: string
    description: string
    entity_count: number
    relationship_count: number
    document_count: number
    status: string
    created_at: string
  }>
  total: number
}

const kbResponse: MockKbResponse = {
  items: [
    {
      id: 'kb-1',
      name: 'Medicare KB',
      description: '',
      entity_count: 0,
      relationship_count: 0,
      document_count: 0,
      status: 'ready',
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
  total: 1,
}

function makeSseStream(events: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  let i = 0
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i >= events.length) {
        controller.close()
        return
      }
      controller.enqueue(encoder.encode(events[i]))
      i += 1
    },
  })
}

interface Mounted {
  container: HTMLDivElement
  root: Root
  unmount: () => void
}

function mount(node: ReactNode): Mounted {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(<>{node}</>)
  })
  return {
    container,
    root,
    unmount: () => {
      act(() => {
        root.unmount()
      })
      container.remove()
    },
  }
}

async function flush(times = 8): Promise<void> {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise<void>((resolve) => {
        setTimeout(resolve, 0)
      })
    })
  }
}

function withProviders(node: ReactNode): React.ReactElement {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('RagChat', () => {
  const realFetch = global.fetch

  beforeEach(() => {
    useChatStore.setState({ conversations: {}, activeConversationId: null })
  })

  afterEach(() => {
    global.fetch = realFetch
    vi.restoreAllMocks()
  })

  it('streams an SSE response and renders citations as links', async () => {
    const fetchMock = vi.fn(
      (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        void init
        const url = typeof input === 'string' ? input : input.toString()
        if (url.endsWith('/knowledgebases')) {
          return Promise.resolve(
            new Response(JSON.stringify(kbResponse), {
              status: 200,
              headers: { 'content-type': 'application/json' },
            }),
          )
        }
        if (url.includes('/chat/conversations/')) {
          const stream = makeSseStream([
            'data: {"token": "Hello", "done": false}\n\n',
            'data: {"token": " world", "done": false}\n\n',
            'data: {"token": "", "done": true, "sources": ["entity-7"]}\n\n',
          ])
          return Promise.resolve(
            new Response(stream, {
              status: 200,
              headers: { 'content-type': 'text/event-stream' },
            }),
          )
        }
        return Promise.resolve(new Response('{}', { status: 200 }))
      },
    )
    global.fetch = fetchMock as unknown as typeof fetch

    const handle = mount(withProviders(<RagChat />))
    await flush(20)

    const select = handle.container.querySelector(
      '[data-testid="kb-selector"]',
    ) as HTMLSelectElement | null
    expect(select).not.toBeNull()
    expect(select?.value).toBe('kb-1')

    const input = handle.container.querySelector(
      '[data-testid="chat-input"]',
    ) as HTMLTextAreaElement
    const form = input.closest('form') as HTMLFormElement

    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      'value',
    )?.set
    act(() => {
      nativeSetter?.call(input, 'who is fraudster?')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    act(() => {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })
    await flush(40)

    expect(handle.container.textContent ?? '').toContain('Hello world')
    const citation = handle.container.querySelector(
      '[data-testid="citation-link"]',
    )
    expect(citation).not.toBeNull()
    expect(citation?.getAttribute('href')).toBe(
      '/investigation?entity_id=entity-7',
    )

    const chatCalls = fetchMock.mock.calls.filter(([url]) => {
      const u = typeof url === 'string' ? url : String(url)
      return u.includes('/chat/conversations/')
    })
    expect(chatCalls).toHaveLength(1)
    const [chatUrl, init] = chatCalls[0]
    expect(String(chatUrl)).toContain('stream=true')
    expect((init as RequestInit | undefined)?.method).toBe('POST')

    handle.unmount()
  })

  it('exposes the KB selector populated from /knowledgebases', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify(kbResponse), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    ) as typeof fetch

    const handle = mount(withProviders(<RagChat />))
    await flush(20)
    const options = handle.container.querySelectorAll(
      '[data-testid="kb-selector"] option',
    )
    expect(options.length).toBeGreaterThan(0)
    expect(options[0].textContent).toContain('Medicare KB')
    handle.unmount()
  })
})
