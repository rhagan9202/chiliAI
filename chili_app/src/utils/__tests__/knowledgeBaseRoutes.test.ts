import { describe, expect, it } from 'vitest'

import {
  knowledgeBaseSelectionTarget,
  knowledgeBaseWorkspacePath,
  legacyWorkspaceRedirect,
  matchWorkspacePath,
} from '../knowledgeBaseRoutes'

describe('knowledgeBaseWorkspacePath', () => {
  it('defaults to the overview section, which has no path segment', () => {
    expect(knowledgeBaseWorkspacePath('kb-1')).toBe('/knowledge-bases/kb-1')
  })

  it('appends the section for every other section', () => {
    expect(knowledgeBaseWorkspacePath('kb-1', 'data')).toBe('/knowledge-bases/kb-1/data')
    expect(knowledgeBaseWorkspacePath('kb-1', 'runs')).toBe('/knowledge-bases/kb-1/runs')
  })

  it('encodes ids that are not URL-safe', () => {
    expect(knowledgeBaseWorkspacePath('a b/c', 'add')).toBe('/knowledge-bases/a%20b%2Fc/add')
  })
})

describe('matchWorkspacePath', () => {
  it('reads the id and defaults to overview', () => {
    expect(matchWorkspacePath('/knowledge-bases/kb-1')).toEqual({
      knowledgeBaseId: 'kb-1',
      section: 'overview',
    })
  })

  it('reads the section when present, and decodes the id', () => {
    expect(matchWorkspacePath('/knowledge-bases/a%20b/settings')).toEqual({
      knowledgeBaseId: 'a b',
      section: 'settings',
    })
  })

  it('tolerates a trailing slash', () => {
    expect(matchWorkspacePath('/knowledge-bases/kb-1/')).toEqual({
      knowledgeBaseId: 'kb-1',
      section: 'overview',
    })
  })

  it('does not match the library itself', () => {
    expect(matchWorkspacePath('/knowledge-bases')).toBeNull()
    expect(matchWorkspacePath('/knowledge-bases/')).toBeNull()
  })

  it('does not match an unknown section or a deeper path', () => {
    expect(matchWorkspacePath('/knowledge-bases/kb-1/bogus')).toBeNull()
    expect(matchWorkspacePath('/knowledge-bases/kb-1/data/extra')).toBeNull()
  })

  it('does not match another page', () => {
    expect(matchWorkspacePath('/alerts')).toBeNull()
    expect(matchWorkspacePath('/knowledge-basesX/kb-1')).toBeNull()
  })

  it('returns null for malformed percent-encoding in the id', () => {
    expect(matchWorkspacePath('/knowledge-bases/%')).toBeNull()
  })
})

describe('legacyWorkspaceRedirect', () => {
  it('sends ?kb= to that knowledge base overview', () => {
    expect(legacyWorkspaceRedirect(new URLSearchParams('kb=kb-1'))).toBe(
      '/knowledge-bases/kb-1',
    )
  })

  it('sends ?kb=&document= to the data section, carrying the chunk', () => {
    expect(
      legacyWorkspaceRedirect(new URLSearchParams('kb=kb-1&document=doc-9&chunk=3')),
    ).toBe('/knowledge-bases/kb-1/data?document=doc-9&chunk=3')
  })

  it('drops a document without a knowledge base — it addresses nothing', () => {
    expect(legacyWorkspaceRedirect(new URLSearchParams('document=doc-9'))).toBeNull()
  })

  it('returns null when there is nothing legacy to redirect', () => {
    expect(legacyWorkspaceRedirect(new URLSearchParams())).toBeNull()
  })
})

describe('knowledgeBaseSelectionTarget', () => {
  it('keeps the current section when switching knowledge base inside a workspace', () => {
    expect(knowledgeBaseSelectionTarget('/knowledge-bases/kb-1/runs', 'kb-2')).toBe(
      '/knowledge-bases/kb-2/runs',
    )
  })

  it('opens a workspace when selecting from the library', () => {
    expect(knowledgeBaseSelectionTarget('/knowledge-bases', 'kb-2')).toBe(
      '/knowledge-bases/kb-2',
    )
  })

  it('returns null elsewhere, where the selection belongs in ?kb=', () => {
    expect(knowledgeBaseSelectionTarget('/alerts', 'kb-2')).toBeNull()
    expect(knowledgeBaseSelectionTarget('/investigation/e-1', 'kb-2')).toBeNull()
  })
})
