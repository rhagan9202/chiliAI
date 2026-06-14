import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, useEffect } from 'react'
import { createRoot, type Root } from 'react-dom/client'

import { useChatMessages, type UseChatMessagesResult } from '../useChatMessages'
import { useChatStore } from '../../stores/chatStore'

interface RenderHandle {
  current: UseChatMessagesResult | null
  unmount: () => void
}

function renderUseChatMessages(): RenderHandle {
  const handle: RenderHandle = {
    current: null,
    unmount: () => {},
  }

  function HookHost(): null {
    const result = useChatMessages()
    useEffect(() => {
      handle.current = result
    })
    return null
  }

  const container = document.createElement('div')
  document.body.appendChild(container)
  const root: Root = createRoot(container)
  act(() => {
    root.render(<HookHost />)
  })

  handle.unmount = (): void => {
    act(() => {
      root.unmount()
    })
    container.remove()
  }
  return handle
}

describe('useChatMessages', () => {
  beforeEach(() => {
    useChatStore.setState({
      conversations: {},
      activeConversationId: null,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('posts streaming chat messages without stale knowledge-base fields', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response('data: {"done": true, "sources": []}\n\n', {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const handle = renderUseChatMessages()

    await act(async () => {
      await handle.current?.send({
        conversationId: 'conversation-1',
        content: 'Find unusual claims',
      })
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(String(init?.body))).toEqual({ content: 'Find unusual claims' })
    handle.unmount()
  })
})
