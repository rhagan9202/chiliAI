import { describe, expect, it } from 'vitest'

import {
  knowledgeBaseStatusHint,
  knowledgeBaseStatusLabel,
} from '../knowledgeBaseStatus'

describe('knowledgeBaseStatusLabel', () => {
  it('names the empty state so it cannot be mistaken for a working knowledge base', () => {
    // The API's `active` means "created, nothing ingested" — the opposite of
    // what the word suggests next to `ready`.
    expect(knowledgeBaseStatusLabel('active')).toBe('Empty')
  })

  it('names the in-progress state', () => {
    expect(knowledgeBaseStatusLabel('building')).toBe('Building')
  })

  it('names the queryable state', () => {
    expect(knowledgeBaseStatusLabel('ready')).toBe('Ready')
  })

  it('names the failed state in analyst words', () => {
    expect(knowledgeBaseStatusLabel('error')).toBe('Failed')
  })

  it('names the archived state', () => {
    expect(knowledgeBaseStatusLabel('archived')).toBe('Archived')
  })

  it('humanizes an unrecognized status rather than showing a raw key', () => {
    expect(knowledgeBaseStatusLabel('pending_cleanup')).toBe('Pending cleanup')
  })
})

describe('knowledgeBaseStatusHint', () => {
  it('explains what empty means', () => {
    expect(knowledgeBaseStatusHint('active')).toBe(
      'Created, but nothing has been ingested yet.',
    )
  })

  it('explains what ready means', () => {
    expect(knowledgeBaseStatusHint('ready')).toBe(
      'Entities and relationships are available to search, chart and chat against.',
    )
  })

  it('returns an empty hint for an unrecognized status', () => {
    expect(knowledgeBaseStatusHint('pending_cleanup')).toBe('')
  })
})
