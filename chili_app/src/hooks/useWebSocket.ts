// Generic WebSocket hook with auto-reconnect and typed message dispatch.
//
// The hook owns the lifecycle of a single `WebSocket`. Incoming messages are
// JSON-decoded and forwarded to `onMessage`. Disconnects trigger an
// exponential-backoff reconnect loop bounded by `maxRetries`.

import { useEffect, useRef, useState } from 'react'

import type { ConnectionStatus } from '../types/wsEvents'

export interface UseWebSocketOptions {
  maxRetries?: number
  baseDelayMs?: number
  maxDelayMs?: number
  // Test seam: factory used to construct the WebSocket. Defaults to the
  // global `WebSocket` constructor; tests override with a stub.
  socketFactory?: (url: string) => WebSocket
  // Test seam: build the absolute URL from the relative `path`. Defaults to
  // deriving from `window.location`.
  urlBuilder?: (path: string) => string
}

export interface UseWebSocketResult {
  status: ConnectionStatus
  retryCount: number
}

const DEFAULT_MAX_RETRIES = 5
const DEFAULT_BASE_DELAY_MS = 1000
const DEFAULT_MAX_DELAY_MS = 30_000

function defaultUrlBuilder(path: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const normalised = path.startsWith('/') ? path : `/${path}`
  return `${protocol}//${host}${normalised}`
}

function defaultSocketFactory(url: string): WebSocket {
  return new WebSocket(url)
}

export function useWebSocket<E>(
  path: string,
  onMessage: (event: E) => void,
  opts: UseWebSocketOptions = {},
): UseWebSocketResult {
  const {
    maxRetries = DEFAULT_MAX_RETRIES,
    baseDelayMs = DEFAULT_BASE_DELAY_MS,
    maxDelayMs = DEFAULT_MAX_DELAY_MS,
    socketFactory = defaultSocketFactory,
    urlBuilder = defaultUrlBuilder,
  } = opts

  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [retryCount, setRetryCount] = useState<number>(0)

  // Ref the callback so reconnect loops don't tear down on every render.
  const onMessageRef = useRef(onMessage)
  useEffect(() => {
    onMessageRef.current = onMessage
  }, [onMessage])

  useEffect(() => {
    let cancelled = false
    let socket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0

    const connect = (): void => {
      if (cancelled) {
        return
      }
      const url = urlBuilder(path)
      setStatus(attempt === 0 ? 'connecting' : 'reconnecting')
      let nextSocket: WebSocket
      try {
        nextSocket = socketFactory(url)
      } catch {
        scheduleReconnect()
        return
      }
      socket = nextSocket

      nextSocket.onopen = (): void => {
        if (cancelled) {
          return
        }
        attempt = 0
        setRetryCount(0)
        setStatus('open')
      }

      nextSocket.onmessage = (event: MessageEvent<unknown>): void => {
        if (cancelled) {
          return
        }
        const raw = typeof event.data === 'string' ? event.data : null
        if (raw === null) {
          return
        }
        let parsed: unknown
        try {
          parsed = JSON.parse(raw)
        } catch {
          return
        }
        // Skip backend keep-alive frames (`{"type":"ping"}`).
        if (
          parsed !== null &&
          typeof parsed === 'object' &&
          (parsed as { type?: unknown }).type === 'ping'
        ) {
          return
        }
        onMessageRef.current(parsed as E)
      }

      nextSocket.onclose = (): void => {
        if (cancelled) {
          return
        }
        socket = null
        scheduleReconnect()
      }

      nextSocket.onerror = (): void => {
        // Browsers fire a generic Event with no detail; the close handler
        // will run next and own the reconnect decision.
      }
    }

    const scheduleReconnect = (): void => {
      if (cancelled) {
        return
      }
      if (attempt >= maxRetries) {
        setStatus('closed')
        return
      }
      const delay = Math.min(maxDelayMs, baseDelayMs * 2 ** attempt)
      attempt += 1
      setRetryCount(attempt)
      setStatus('reconnecting')
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        connect()
      }, delay)
    }

    connect()

    return (): void => {
      cancelled = true
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      if (socket !== null) {
        socket.onopen = null
        socket.onmessage = null
        socket.onclose = null
        socket.onerror = null
        try {
          socket.close()
        } catch {
          // ignore
        }
        socket = null
      }
    }
  }, [path, maxRetries, baseDelayMs, maxDelayMs, socketFactory, urlBuilder])

  return { status, retryCount }
}

export default useWebSocket
