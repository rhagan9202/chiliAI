import { useState } from 'react'

function newConversationId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `conv-${Math.random().toString(36).slice(2)}-${Date.now()}`
}

export function useSessionConversationId(): string {
  const [id] = useState<string>(() => newConversationId())
  return id
}
