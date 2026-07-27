import type { PackTransport } from '../../api/contracts'

/**
 * Compare the event transport a candidate pack would run on against the active
 * one (UXA-404).
 *
 * The reload signal itself survives a transport change — the API publishes
 * `config.updated` on the *pre-swap* transport deliberately, and the worker
 * rebinds when it rebuilds its dependencies. What does not survive is anything
 * already queued on the old stream or consumer group: after the rebind nothing
 * consumes it. And if the new transport is unreachable the worker keeps its
 * previous dependencies and logs `CONFIG RELOAD FAILED`, leaving the API on the
 * new pack and the worker on the old one with nothing said in the UI.
 *
 * Both sides must be the *effective* transport, which is why the candidate's
 * comes from the API rather than being read out of the pack's YAML: the
 * environment wins whenever a pack's `events` section is absent or equal to the
 * default, so a pack that simply omits it changes nothing.
 */

/** The active side, as `/config/domain` reports it (a `DomainConfig.events`). */
export interface ActiveTransport {
  backend?: string | null
  uri?: string | null
  stream_prefix?: string | null
  consumer_group?: string | null
}

export interface TransportChange {
  field: string
  from: string
  to: string
}

export interface TransportDelta {
  changes: TransportChange[]
  /**
   * `none` — nothing differs, or either side is unknown.
   * `changed` — queued work on the current stream is abandoned.
   * `decoupled` — either side is in-memory: the API and worker are separate
   *   processes, so each builds its own in-process bus and the pipeline stops.
   */
  severity: 'none' | 'changed' | 'decoupled'
}

const NONE: TransportDelta = { changes: [], severity: 'none' }

/**
 * `DomainConfig.events.backend` spells it `in_memory`; `EventBusSettings`
 * (what the API resolves a pack to) spells it `in-memory`. Compare on one form
 * or every swap between the two shapes reads as a change.
 */
function normalizeBackend(value: string | null | undefined): string {
  return (value ?? '').replace(/_/g, '-')
}

function isInMemory(value: string | null | undefined): boolean {
  return normalizeBackend(value) === 'in-memory'
}

/** An unset URI and an empty one are the same absence. */
function normalizeUri(value: string | null | undefined): string {
  return value ?? ''
}

export function transportDelta(
  active: ActiveTransport | null | undefined,
  candidate: PackTransport | null | undefined,
): TransportDelta {
  // Unknown is not a claim of change: an invalid pack reports no transport, and
  // warning on it would be inventing a difference we cannot see.
  if (!active || !candidate) {
    return NONE
  }

  const changes: TransportChange[] = []
  const compare = (field: string, from: string, to: string) => {
    if (from !== to) {
      changes.push({ field, from, to })
    }
  }

  compare('backend', normalizeBackend(active.backend), normalizeBackend(candidate.backend))
  compare('uri', normalizeUri(active.uri), normalizeUri(candidate.uri))
  compare('stream_prefix', active.stream_prefix ?? '', candidate.stream_prefix ?? '')
  compare('consumer_group', active.consumer_group ?? '', candidate.consumer_group ?? '')

  if (changes.length === 0) {
    return NONE
  }

  const decoupled = isInMemory(active.backend) || isInMemory(candidate.backend)
  return { changes, severity: decoupled ? 'decoupled' : 'changed' }
}

/** Rendered form of an absent value, so a delta never shows an empty cell. */
export function transportValueLabel(value: string): string {
  return value === '' ? 'none' : value
}
