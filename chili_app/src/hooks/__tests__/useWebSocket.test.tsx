import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, useEffect } from 'react'
import { createRoot, type Root } from 'react-dom/client'

import { useWebSocket } from '../useWebSocket'
import type { UseWebSocketOptions, UseWebSocketResult } from '../useWebSocket'

type Listener<E> = ((event: E) => void) | null

class FakeSocket {
  static instances: FakeSocket[] = []

  url: string
  readyState: number = 0
  onopen: Listener<Event> = null
  onclose: Listener<CloseEvent> = null
  onmessage: Listener<MessageEvent<unknown>> = null
  onerror: Listener<Event> = null

  constructor(url: string) {
    this.url = url
    FakeSocket.instances.push(this)
  }

  open(): void {
    this.readyState = 1
    this.onopen?.(new Event('open'))
  }

  emit(data: unknown): void {
    const payload = typeof data === 'string' ? data : JSON.stringify(data)
    this.onmessage?.(new MessageEvent('message', { data: payload }))
  }

  emitRaw(payload: string): void {
    this.onmessage?.(new MessageEvent('message', { data: payload }))
  }

  close(): void {
    if (this.readyState === 3) {
      return
    }
    this.readyState = 3
    this.onclose?.(new CloseEvent('close'))
  }
}

function makeFactory(): (url: string) => WebSocket {
  return (url: string) => new FakeSocket(url) as unknown as WebSocket
}

const urlBuilder = (path: string): string => `ws://test.local${path}`

interface RenderHandle<T> {
  current: { value: T }
  unmount: () => void
}

function renderHookSync<E>(
  path: string,
  onMessage: (event: E) => void,
  opts: UseWebSocketOptions,
): RenderHandle<UseWebSocketResult> {
  const handle: RenderHandle<UseWebSocketResult> = {
    current: { value: { status: 'connecting', retryCount: 0 } },
    unmount: () => {},
  }

  function HookHost(): null {
    const result = useWebSocket<E>(path, onMessage, opts)
    useEffect(() => {
      handle.current.value = result
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

describe('useWebSocket', () => {
  beforeEach(() => {
    FakeSocket.instances = []
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('opens a connection and dispatches parsed JSON messages', () => {
    const onMessage = vi.fn<(event: unknown) => void>()
    const handle = renderHookSync('/ws/alerts', onMessage, {
      socketFactory: makeFactory(),
      urlBuilder,
    })

    expect(FakeSocket.instances).toHaveLength(1)
    const socket = FakeSocket.instances[0]
    expect(socket.url).toBe('ws://test.local/ws/alerts')
    expect(handle.current.value.status).toBe('connecting')

    act(() => {
      socket.open()
    })
    expect(handle.current.value.status).toBe('open')

    act(() => {
      socket.emit({ event_type: 'alert.created', alert: { id: 'a1' } })
    })
    expect(onMessage).toHaveBeenCalledWith({
      event_type: 'alert.created',
      alert: { id: 'a1' },
    })
    handle.unmount()
  })

  it('drops keep-alive ping frames without invoking the callback', () => {
    const onMessage = vi.fn<(event: unknown) => void>()
    const handle = renderHookSync('/ws/alerts', onMessage, {
      socketFactory: makeFactory(),
      urlBuilder,
    })
    const socket = FakeSocket.instances[0]
    act(() => {
      socket.open()
      socket.emit({ type: 'ping' })
    })
    expect(onMessage).not.toHaveBeenCalled()
    handle.unmount()
  })

  it('ignores malformed JSON frames', () => {
    const onMessage = vi.fn<(event: unknown) => void>()
    const handle = renderHookSync('/ws/alerts', onMessage, {
      socketFactory: makeFactory(),
      urlBuilder,
    })
    const socket = FakeSocket.instances[0]
    act(() => {
      socket.open()
      socket.emitRaw('not-json')
    })
    expect(onMessage).not.toHaveBeenCalled()
    handle.unmount()
  })

  it('reconnects with exponential backoff after a close', () => {
    const onMessage = vi.fn<(event: unknown) => void>()
    const handle = renderHookSync('/ws/alerts', onMessage, {
      maxRetries: 3,
      baseDelayMs: 100,
      maxDelayMs: 5000,
      socketFactory: makeFactory(),
      urlBuilder,
    })

    const first = FakeSocket.instances[0]
    act(() => {
      first.open()
      first.close()
    })
    expect(handle.current.value.status).toBe('reconnecting')
    expect(handle.current.value.retryCount).toBe(1)

    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(FakeSocket.instances).toHaveLength(2)

    act(() => {
      FakeSocket.instances[1].close()
    })
    expect(handle.current.value.retryCount).toBe(2)

    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(FakeSocket.instances).toHaveLength(3)
    handle.unmount()
  })

  it('stops retrying after the maxRetries limit', () => {
    const handle = renderHookSync<unknown>('/ws/alerts', () => {}, {
      maxRetries: 2,
      baseDelayMs: 50,
      socketFactory: makeFactory(),
      urlBuilder,
    })

    act(() => {
      FakeSocket.instances[0].close()
    })
    act(() => {
      vi.advanceTimersByTime(50)
    })
    act(() => {
      FakeSocket.instances[1].close()
    })
    act(() => {
      vi.advanceTimersByTime(100)
    })
    act(() => {
      FakeSocket.instances[2].close()
    })

    expect(handle.current.value.status).toBe('closed')
    expect(handle.current.value.retryCount).toBe(2)
    expect(FakeSocket.instances).toHaveLength(3)
    handle.unmount()
  })

  it('cleans up the socket on unmount', () => {
    const handle = renderHookSync<unknown>('/ws/alerts', () => {}, {
      socketFactory: makeFactory(),
      urlBuilder,
    })

    const socket = FakeSocket.instances[0]
    act(() => {
      socket.open()
    })
    handle.unmount()
    expect(socket.readyState).toBe(3)
  })
})
