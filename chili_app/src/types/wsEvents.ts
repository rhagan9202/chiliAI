// WebSocket event payload types broadcast by the backend.
// Discriminated union on `event_type`. Mirrors backend events emitted by
// `backend/api/routers/ws.py` and `backend/events/types.py`.

import type { Alert } from './api'

export interface WsAlertCreated {
  event_type: 'alert.created'
  alert: Alert
}

export interface WsPipelineProgress {
  event_type: 'pipeline.progress'
  knowledge_base_id: string
  batch_id: string
  stage: string
  progress: number
  message?: string | null
}

export interface WsPing {
  type: 'ping'
}

export type WsEvent = WsAlertCreated | WsPipelineProgress

export type ConnectionStatus =
  | 'connecting'
  | 'open'
  | 'closed'
  | 'reconnecting'

export function isWsEvent(value: unknown): value is WsEvent {
  if (value === null || typeof value !== 'object') {
    return false
  }
  const candidate = value as { event_type?: unknown }
  return (
    candidate.event_type === 'alert.created' ||
    candidate.event_type === 'pipeline.progress'
  )
}

export function isWsPing(value: unknown): value is WsPing {
  if (value === null || typeof value !== 'object') {
    return false
  }
  return (value as { type?: unknown }).type === 'ping'
}
