import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import type { RealtimeSnapshotResponse } from './contracts'
import { useUiStore } from '../stores/uiStore'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export function useRealtimeWorkspaceStream() {
  const queryClient = useQueryClient()
  const setRealtimeConnected = useUiStore((state) => state.setRealtimeConnected)
  const setLastRealtimeEventAt = useUiStore((state) => state.setLastRealtimeEventAt)

  useEffect(() => {
    // withCredentials sends the chiliai_session cookie cross-origin so the
    // server-side require_role("viewer") guard on /events/stream can identify
    // the user. Without this, EventSource omits cookies and the stream 401s.
    const eventSource = new EventSource(`${API_BASE_URL}/events/stream`, {
      withCredentials: true,
    })

    const handleWorkspaceUpdate = (event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as RealtimeSnapshotResponse
      setRealtimeConnected(true)
      setLastRealtimeEventAt(payload.emitted_at)

      void queryClient.invalidateQueries({ queryKey: ['alerts'] })
      void queryClient.invalidateQueries({ queryKey: ['workflows'] })
      void queryClient.invalidateQueries({ queryKey: ['analytics'] })
      void queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
      void queryClient.invalidateQueries({ queryKey: ['policy'] })
    }

    eventSource.onopen = () => {
      setRealtimeConnected(true)
    }
    eventSource.addEventListener('workspace-update', handleWorkspaceUpdate)

    eventSource.onerror = () => {
      setRealtimeConnected(false)
    }

    return () => {
      eventSource.removeEventListener('workspace-update', handleWorkspaceUpdate)
      eventSource.close()
      setRealtimeConnected(false)
    }
  }, [queryClient, setLastRealtimeEventAt, setRealtimeConnected])
}