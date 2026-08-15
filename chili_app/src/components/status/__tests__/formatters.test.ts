import { describe, expect, it } from 'vitest'

import { formatFileSize, formatRelativeTime, formatTimestamp } from '../formatters'

describe('formatTimestamp', () => {
  it('formats an ISO string as local medium date + short time', () => {
    expect(formatTimestamp('2026-08-14T20:33:01.208754Z')).toMatch(/Aug 14, 2026/)
  })
  it('returns placeholder for null', () => {
    expect(formatTimestamp(null)).toBe('Not yet recorded')
  })
})

describe('formatRelativeTime', () => {
  const now = new Date('2026-08-14T21:00:00Z')
  it('says just now under a minute', () => {
    expect(formatRelativeTime('2026-08-14T20:59:40Z', now)).toBe('just now')
  })
  it('uses minutes under an hour', () => {
    expect(formatRelativeTime('2026-08-14T20:44:00Z', now)).toBe('16m ago')
  })
  it('uses hours under a day', () => {
    expect(formatRelativeTime('2026-08-14T18:00:00Z', now)).toBe('3h ago')
  })
  it('falls back to absolute beyond 24h', () => {
    expect(formatRelativeTime('2026-08-01T18:00:00Z', now)).toMatch(/Aug 1, 2026/)
  })
  it('returns placeholder for null', () => {
    expect(formatRelativeTime(null, now)).toBe('Not yet recorded')
  })
})

describe('formatFileSize', () => {
  it('formats bytes, KB, MB', () => {
    expect(formatFileSize(579)).toBe('579 B')
    expect(formatFileSize(1442)).toBe('1.4 KB')
    expect(formatFileSize(2.3 * 1024 * 1024)).toBe('2.3 MB')
  })
  it('handles null/undefined/zero', () => {
    expect(formatFileSize(null)).toBe('Unknown size')
    expect(formatFileSize(undefined)).toBe('Unknown size')
    expect(formatFileSize(0)).toBe('Unknown size')
  })
})
