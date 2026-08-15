import { Chip } from '../ui/Chip'
import { statusToken } from './statusTokens'
import type { StatusKind } from './statusTokens'

/** Renders a lifecycle state through the shared token map (label, tone, hint). */
export function StatusChip({
  kind,
  status,
  testId,
}: {
  kind: StatusKind
  status: string
  testId?: string
}) {
  const token = statusToken(kind, status)
  return (
    <Chip label={token.label} testId={testId} title={token.hint || undefined} tone={token.tone} />
  )
}
