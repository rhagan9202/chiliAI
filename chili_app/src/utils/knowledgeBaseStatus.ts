/**
 * Human labels for the knowledge base lifecycle.
 *
 * The API's status vocabulary reads backwards to an analyst: `active` is the
 * *empty* state (created, nothing ingested) and only becomes `ready` once the
 * graph holds entities — see `backend/api/_kb_projection.py::_derive_status`.
 * Rendering the raw values side by side invited the reading that `active` was
 * the healthy one, so the UI names the states instead.
 */

interface StatusCopy {
  label: string
  hint: string
}

const STATUS_COPY: Record<string, StatusCopy> = {
  active: {
    label: 'Empty',
    hint: 'Created, but nothing has been ingested yet.',
  },
  building: {
    label: 'Building',
    hint: 'Documents and records have arrived; the graph is still being built.',
  },
  ready: {
    label: 'Ready',
    hint: 'Entities and relationships are available to search, chart and chat against.',
  },
  error: {
    label: 'Failed',
    hint: 'The last ingestion run did not finish. Open the run timeline for the reason.',
  },
  archived: {
    label: 'Archived',
    hint: 'Kept for reference. It is not offered for new work.',
  },
}

/** Sentence-cases an unknown status key so no raw snake_case reaches the UI. */
function humanize(status: string): string {
  const words = status.replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function knowledgeBaseStatusLabel(status: string): string {
  return STATUS_COPY[status]?.label ?? humanize(status)
}

export function knowledgeBaseStatusHint(status: string): string {
  return STATUS_COPY[status]?.hint ?? ''
}

/**
 * Minimal shape of a KB summary that `knowledgeBaseOptionLabel` needs. Kept
 * structural so the helper can be exercised from tests without dragging in
 * the full generated `KnowledgeBaseSummaryResponse`.
 */
interface KnowledgeBaseLabelInput {
  id: string
  name: string
  status: string
  entity_count?: number | null
  created_at?: string | null
}

/**
 * Label a KB dropdown option so users can tell duplicates apart.
 *
 * Bulk-loaded reference sets (NPPES, DE-SynPUF) legitimately produce several
 * KBs called "TN Demo" — a plain `${name} · ${status}` label collapses them
 * into indistinguishable rows in the Investigation and RAG-chat selectors.
 * When the name is not unique in the choice set the label appends the entity
 * count (and, if still tied, the KB's short id) so the analyst can pick the
 * intended workspace without going to the KB manager.
 */
export function knowledgeBaseOptionLabel(
  target: KnowledgeBaseLabelInput,
  choices: readonly KnowledgeBaseLabelInput[],
): string {
  const statusLabel = knowledgeBaseStatusLabel(target.status)
  const duplicates = choices.filter((kb) => kb.name === target.name)
  if (duplicates.length <= 1) {
    return `${target.name} · ${statusLabel}`
  }
  const entityCount = target.entity_count ?? 0
  const countFragment = `${entityCount.toLocaleString()} entities`
  const stillCollides = duplicates.some(
    (kb) => kb.id !== target.id && (kb.entity_count ?? 0) === entityCount,
  )
  const idFragment = stillCollides ? ` · ${target.id.slice(0, 8)}` : ''
  return `${target.name} · ${countFragment} · ${statusLabel}${idFragment}`
}
