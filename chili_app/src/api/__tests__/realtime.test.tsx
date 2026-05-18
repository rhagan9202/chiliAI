import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { RealtimeSnapshotResponse } from '../contracts'
import { useRealtimeWorkspaceStream } from '../realtime'
import { useUiStore } from '../../stores/uiStore'

type WorkspaceUpdateListener = (event: MessageEvent<string>) => void

class FakeEventSource {
  static instances: FakeEventSource[] = []

  readonly url: string
  readonly eventSourceInitDict?: EventSourceInit
  onerror: ((this: EventSource, ev: Event) => unknown) | null = null
  onopen: ((this: EventSource, ev: Event) => unknown) | null = null
  closed = false

  private readonly listeners = new Map<string, Set<WorkspaceUpdateListener>>()

  constructor(url: string | URL, eventSourceInitDict?: EventSourceInit) {
    this.url = url.toString()
    this.eventSourceInitDict = eventSourceInitDict
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject | null): void {
    if (listener === null || typeof listener !== 'function') {
      return
    }
    const listeners = this.listeners.get(type) ?? new Set<WorkspaceUpdateListener>()
    listeners.add(listener as WorkspaceUpdateListener)
    this.listeners.set(type, listeners)
  }

  removeEventListener(type: string, listener: EventListenerOrEventListenerObject | null): void {
    if (listener === null || typeof listener !== 'function') {
      return
    }
    this.listeners.get(type)?.delete(listener as WorkspaceUpdateListener)
  }

  close(): void {
    this.closed = true
  }

  open(): void {
    this.onopen?.call(this as unknown as EventSource, new Event('open'))
  }

  error(): void {
    this.onerror?.call(this as unknown as EventSource, new Event('error'))
  }

  emitWorkspaceUpdate(payload: RealtimeSnapshotResponse): void {
    const event = new MessageEvent<string>('workspace-update', {
      data: JSON.stringify(payload),
    })
    this.listeners.get('workspace-update')?.forEach((listener) => listener(event))
  }
}

const baseSnapshot: RealtimeSnapshotResponse = {
  sequence: 1,
  emitted_at: '2026-05-18T10:00:00Z',
  active_alerts: 1,
  running_workflows: 1,
  knowledge_base_statuses: {
    'kb-1': 'processing',
  },
}

function renderRealtimeHook(queryClient: QueryClient) {
  function Wrapper({ children }: { children: ReactNode }): React.ReactElement {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }

  return renderHook(() => useRealtimeWorkspaceStream(), { wrapper: Wrapper })
}

describe('useRealtimeWorkspaceStream', () => {
  const originalEventSource = globalThis.EventSource

  beforeEach(() => {
    vi.useFakeTimers()
    FakeEventSource.instances = []
    globalThis.EventSource = FakeEventSource as unknown as typeof EventSource
    useUiStore.setState({
      lastRealtimeEventAt: null,
      realtimeConnected: false,
    })
  })

  afterEach(() => {
    globalThis.EventSource = originalEventSource
    vi.useRealTimers()
  })

  it('connects with credentials and records the latest realtime event timestamp', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const { unmount } = renderRealtimeHook(queryClient)
    const eventSource = FakeEventSource.instances[0]

    expect(eventSource.url).toMatch(/\/events\/stream$/)
    expect(eventSource.eventSourceInitDict).toEqual({ withCredentials: true })

    act(() => {
      eventSource.open()
      eventSource.emitWorkspaceUpdate(baseSnapshot)
    })

    expect(useUiStore.getState().realtimeConnected).toBe(true)
    expect(useUiStore.getState().lastRealtimeEventAt).toBe(baseSnapshot.emitted_at)
    expect(invalidateSpy).not.toHaveBeenCalled()

    unmount()
    expect(eventSource.closed).toBe(true)
    expect(useUiStore.getState().realtimeConnected).toBe(false)
  })

  it('invalidates only queries affected by realtime snapshot changes', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    renderRealtimeHook(queryClient)
    const eventSource = FakeEventSource.instances[0]

    act(() => {
      eventSource.emitWorkspaceUpdate(baseSnapshot)
      eventSource.emitWorkspaceUpdate({
        sequence: 2,
        emitted_at: '2026-05-18T10:00:05Z',
        active_alerts: 2,
        running_workflows: 0,
        knowledge_base_statuses: {
          'kb-1': 'ready',
          'kb-2': 'processing',
        },
      })
    })

    const invalidatedKeys = invalidateSpy.mock.calls.map(([filters]) => {
      expect(filters).toBeDefined()
      return filters?.queryKey
    })

    expect(invalidatedKeys).toEqual([
      ['alerts'],
      ['workflows'],
      ['knowledge-bases'],
      ['knowledge-bases', 'kb-1'],
      ['knowledge-bases', 'kb-1', 'documents'],
      ['knowledge-bases', 'kb-2'],
      ['knowledge-bases', 'kb-2', 'documents'],
    ])
    expect(invalidatedKeys).not.toContainEqual(['analytics'])
    expect(invalidatedKeys).not.toContainEqual(['policy'])
  })

  it('does not invalidate queries for unchanged heartbeat snapshots', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    renderRealtimeHook(queryClient)
    const eventSource = FakeEventSource.instances[0]

    act(() => {
      eventSource.emitWorkspaceUpdate(baseSnapshot)
      eventSource.emitWorkspaceUpdate({
        ...baseSnapshot,
        sequence: 2,
        emitted_at: '2026-05-18T10:00:05Z',
      })
    })

    expect(invalidateSpy).not.toHaveBeenCalled()
  })

  it('closes broken streams and reconnects with backoff', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    renderRealtimeHook(queryClient)
    const firstEventSource = FakeEventSource.instances[0]

    act(() => {
      firstEventSource.open()
      firstEventSource.error()
    })

    expect(firstEventSource.closed).toBe(true)
    expect(useUiStore.getState().realtimeConnected).toBe(false)
    expect(FakeEventSource.instances).toHaveLength(1)

    act(() => {
      vi.advanceTimersByTime(999)
    })
    expect(FakeEventSource.instances).toHaveLength(1)

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(FakeEventSource.instances).toHaveLength(2)

    const secondEventSource = FakeEventSource.instances[1]
    act(() => {
      secondEventSource.open()
    })
    expect(useUiStore.getState().realtimeConnected).toBe(true)
  })

  it('cleans up pending reconnect timers on unmount', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { unmount } = renderRealtimeHook(queryClient)
    const firstEventSource = FakeEventSource.instances[0]

    act(() => {
      firstEventSource.error()
    })
    unmount()

    act(() => {
      vi.advanceTimersByTime(1000)
    })

    expect(FakeEventSource.instances).toHaveLength(1)
    expect(firstEventSource.closed).toBe(true)
  })
})
