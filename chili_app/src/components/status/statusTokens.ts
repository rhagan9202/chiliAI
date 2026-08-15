/**
 * One state -> {label, tone, hint} map for every lifecycle the ingestion
 * surfaces render.
 *
 * The page used to flatten three separate backend vocabularies (knowledge
 * base status, the eight-state document lifecycle, workflow run status) with
 * ad-hoc tone helpers, which is how a zero-entity document ended up rendering
 * a green "ready" chip. Encoding the vocabulary once keeps the reading of a
 * state identical wherever it appears.
 */
import {
  knowledgeBaseStatusHint,
  knowledgeBaseStatusLabel,
} from '../../utils/knowledgeBaseStatus'
import type { ChipTone } from '../ui/chipTones'

export type StatusKind = 'knowledge-base' | 'document' | 'workflow'
export type StatusTone = ChipTone
export type StatusToken = { label: string; tone: StatusTone; hint: string }

function inProgress(): StatusToken {
  return {
    label: 'In progress',
    tone: 'warning',
    hint: 'Ingestion is still processing this document.',
  }
}

const DOCUMENT_TOKENS: Record<string, StatusToken> = {
  pending: inProgress(),
  parsing: inProgress(),
  parsed: inProgress(),
  chunked: inProgress(),
  extracted: inProgress(),
  validated: {
    label: 'Validated',
    tone: 'success',
    hint: 'Extraction finished and validated entities landed in the graph.',
  },
  extracted_empty: {
    label: 'No entities',
    tone: 'default',
    hint: 'Parsed cleanly but no domain entities were found — it contributed nothing to the graph.',
  },
  failed: {
    label: 'Failed',
    tone: 'danger',
    hint: 'Ingestion failed; see the error on this row.',
  },
}

const WORKFLOW_TOKENS: Record<string, StatusToken> = {
  queued: { label: 'Queued', tone: 'info', hint: 'Waiting for the worker to pick this run up.' },
  running: { label: 'Running', tone: 'warning', hint: 'The pipeline is executing.' },
  awaiting_approval: {
    label: 'Awaiting approval',
    tone: 'info',
    hint: 'Parked at a human approval gate.',
  },
  completed: { label: 'Completed', tone: 'success', hint: 'All steps finished.' },
  failed: { label: 'Failed', tone: 'danger', hint: 'A step failed; the timeline shows which.' },
  cancelled: { label: 'Cancelled', tone: 'default', hint: 'Stopped before completion.' },
}

/** KB labels/hints come from `knowledgeBaseStatus.ts`; only the tone lives here. */
const KB_TONES: Record<string, StatusTone> = {
  ready: 'success',
  active: 'warning',
  building: 'warning',
  error: 'danger',
  archived: 'default',
}

function sentenceCase(status: string): string {
  const spaced = status.replace(/[_-]+/g, ' ').trim()
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function statusToken(kind: StatusKind, status: string): StatusToken {
  if (kind === 'knowledge-base') {
    return {
      label: knowledgeBaseStatusLabel(status),
      tone: KB_TONES[status] ?? 'default',
      hint: knowledgeBaseStatusHint(status),
    }
  }
  const table = kind === 'document' ? DOCUMENT_TOKENS : WORKFLOW_TOKENS
  return table[status] ?? { label: sentenceCase(status), tone: 'default', hint: '' }
}
