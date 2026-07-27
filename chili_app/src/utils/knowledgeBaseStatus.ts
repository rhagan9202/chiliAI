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
