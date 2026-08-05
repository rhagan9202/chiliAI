import type { ChipTone } from './chipTones'

export type StatusPillTone = ChipTone

export const STATUS_PILL_TONES = [
  'default',
  'info',
  'success',
  'warning',
  'danger',
  'network',
] as const satisfies readonly StatusPillTone[]

const STATUS_TONES: Record<string, StatusPillTone> = {
  acknowledged: 'success',
  active: 'success',
  archived: 'default',
  blocked: 'danger',
  building: 'warning',
  closed: 'success',
  completed: 'success',
  dismissed: 'default',
  error: 'danger',
  failed: 'danger',
  fresh: 'success',
  idle: 'default',
  in_review: 'warning',
  investigating: 'warning',
  open: 'info',
  queued: 'default',
  ready: 'success',
  resolved: 'success',
  running: 'warning',
  stale: 'warning',
  unknown: 'default',
}

const PRIORITY_TONES: Record<string, StatusPillTone> = {
  critical: 'danger',
  high: 'warning',
  low: 'info',
  medium: 'warning',
}

export function statusToneForValue(value: string): StatusPillTone {
  return STATUS_TONES[value.toLowerCase()] ?? 'default'
}

export function priorityToneForValue(value: string): StatusPillTone {
  return PRIORITY_TONES[value.toLowerCase()] ?? statusToneForValue(value)
}
