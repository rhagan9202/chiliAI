import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import type { RealtimeSnapshotResponse } from './contracts'
import { alertsQueryKey } from './alerts'
import {
  knowledgeBaseDetailQueryKey,
  knowledgeBaseDocumentsQueryKey,
  knowledgeBasesQueryKey,
} from './knowledgebases'
import { workflowsQueryKey } from './workflows'
import { API_BASE_URL } from '../lib/apiClient'
import { useUiStore } from '../stores/uiStore'

const INITIAL_RECONNECT_DELAY_MS = 1000
const MAX_RECONNECT_DELAY_MS = 30000

function changedKnowledgeBaseIds(
  previous: RealtimeSnapshotResponse,
  next: RealtimeSnapshotResponse,
): string[] {
  const ids = new Set([
    ...Object.keys(previous.knowledge_base_statuses),
    ...Object.keys(next.knowledge_base_statuses),
  ])

  return [...ids].filter(
    (id) => previous.knowledge_base_statuses[id] !== next.knowledge_base_statuses[id],
  )
}

export function useRealtimeWorkspaceStream() {
  const queryClient = useQueryClient()
  const setRealtimeConnected = useUiStore((state) => state.setRealtimeConnected)
  const setLastRealtimeEventAt = useUiStore((state) => state.setLastRealtimeEventAt)

  useEffect(() => {
    let eventSource: EventSource | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let reconnectDelayMs = INITIAL_RECONNECT_DELAY_MS
    let disposed = false
    let previousSnapshot: RealtimeSnapshotResponse | null = null

    const clearReconnectTimer = () => {
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    const closeEventSource = () => {
      if (eventSource !== null) {
        eventSource.removeEventListener('workspace-update', handleWorkspaceUpdate)
        eventSource.close()
        eventSource = null
      }
    }

    const handleWorkspaceUpdate = (event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as RealtimeSnapshotResponse
      setRealtimeConnected(true)
      setLastRealtimeEventAt(payload.emitted_at)

      if (previousSnapshot !== null) {
        if (previousSnapshot.active_alerts !== payload.active_alerts) {
          void queryClient.invalidateQueries({ queryKey: alertsQueryKey })
        }

        if (previousSnapshot.running_workflows !== payload.running_workflows) {
          void queryClient.invalidateQueries({ queryKey: workflowsQueryKey })
        }

        const changedKnowledgeBases = changedKnowledgeBaseIds(previousSnapshot, payload)
        if (changedKnowledgeBases.length > 0) {
          void queryClient.invalidateQueries({ queryKey: knowledgeBasesQueryKey })
          changedKnowledgeBases.forEach((knowledgeBaseId) => {
            void queryClient.invalidateQueries({
              queryKey: knowledgeBaseDetailQueryKey(knowledgeBaseId),
            })
            void queryClient.invalidateQueries({
              queryKey: knowledgeBaseDocumentsQueryKey(knowledgeBaseId),
            })
          })
        }
      }

      previousSnapshot = payload
    }

    const connect = () => {
      clearReconnectTimer()
      closeEventSource()

      if (disposed) {
        return
      }

      // withCredentials sends the chiliai_session cookie cross-origin so the
      // server-side require_role("viewer") guard on /events/stream can identify
      // the user. Without this, EventSource omits cookies and the stream 401s.
      eventSource = new EventSource(`${API_BASE_URL}/events/stream`, {
        withCredentials: true,
      })

      eventSource.onopen = () => {
        reconnectDelayMs = INITIAL_RECONNECT_DELAY_MS
        setRealtimeConnected(true)
      }
      eventSource.addEventListener('workspace-update', handleWorkspaceUpdate)

      eventSource.onerror = () => {
        if (disposed) {
          return
        }
        setRealtimeConnected(false)
        closeEventSource()
        reconnectTimer = setTimeout(connect, reconnectDelayMs)
        reconnectDelayMs = Math.min(reconnectDelayMs * 2, MAX_RECONNECT_DELAY_MS)
      }
    }

    connect()

    return () => {
      disposed = true
      clearReconnectTimer()
      closeEventSource()
      setRealtimeConnected(false)
    }
  }, [queryClient, setLastRealtimeEventAt, setRealtimeConnected])
}
