import { describe, expect, it } from 'vitest'

import {
  DEFAULT_RISK_QUESTION,
  buildRagChatUrl,
  buildRagMessageFilters,
  citationNavigationTarget,
  parseRagLaunchContext,
} from '../ragContext'

describe('ragContext', () => {
  it('serializes an alert launch context into rag chat query params', () => {
    expect(
      buildRagChatUrl({
        knowledgeBaseId: 'kb-1',
        source: 'alert',
        alertId: 'alert-1',
        entityId: 'provider-204',
        evidencePackId: 'evidence-1',
        question: DEFAULT_RISK_QUESTION,
      }),
    ).toBe(
      '/rag-chat?kb=kb-1&source=alert&alert=alert-1&entity=provider-204&evidence=evidence-1&q=Why+is+this+high+risk%3F',
    )
  })

  it('omits empty values while serializing launch context', () => {
    expect(
      buildRagChatUrl({
        knowledgeBaseId: 'kb-1',
        source: null,
        alertId: '',
        entityId: null,
        caseId: undefined,
        evidencePackId: 'evidence-1',
        question: '',
      }),
    ).toBe('/rag-chat?kb=kb-1&evidence=evidence-1')
  })

  it('returns the bare rag chat URL when no context values are present', () => {
    expect(buildRagChatUrl({ knowledgeBaseId: null, source: null })).toBe('/rag-chat')
  })

  it('parses rag chat query params into typed launch context', () => {
    expect(
      parseRagLaunchContext(
        new URLSearchParams(
          'kb=kb-1&source=case&alert=alert-1&entity=provider-204&case=case-7&evidence=evidence-1&q=Explain+risk',
        ),
      ),
    ).toEqual({
      knowledgeBaseId: 'kb-1',
      source: 'case',
      alertId: 'alert-1',
      entityId: 'provider-204',
      caseId: 'case-7',
      evidencePackId: 'evidence-1',
      installationId: null,
      scorecardRunId: null,
      question: 'Explain risk',
    })
  })

  it('drops empty and unknown parsed launch values', () => {
    expect(parseRagLaunchContext(new URLSearchParams('kb=&source=other&alert='))).toEqual({
      knowledgeBaseId: null,
      source: null,
      alertId: null,
      entityId: null,
      caseId: null,
      evidencePackId: null,
      installationId: null,
      scorecardRunId: null,
      question: null,
    })
  })

  it('serializes and parses a housing launch context', () => {
    const url = buildRagChatUrl({
      knowledgeBaseId: 'kb-housing',
      source: 'housing',
      installationId: 'edwards',
      scorecardRunId: 'run-1',
      question: 'Summarize housing supply risk.',
    })

    expect(url).toBe(
      '/rag-chat?kb=kb-housing&source=housing&installation=edwards&scorecardRun=run-1&q=Summarize+housing+supply+risk.',
    )
    expect(parseRagLaunchContext(new URLSearchParams(url.slice('/rag-chat?'.length)))).toEqual({
      knowledgeBaseId: 'kb-housing',
      source: 'housing',
      alertId: null,
      entityId: null,
      caseId: null,
      evidencePackId: null,
      installationId: 'edwards',
      scorecardRunId: 'run-1',
      question: 'Summarize housing supply risk.',
    })
  })

  it('builds message filters from non-empty launch context values', () => {
    expect(
      buildRagMessageFilters({
        knowledgeBaseId: 'kb-1',
        source: 'alert',
        alertId: 'alert-1',
        entityId: '',
        caseId: null,
        evidencePackId: 'evidence-1',
      }),
    ).toEqual({
      source_type: 'alert',
      alert_id: 'alert-1',
      evidence_pack_id: 'evidence-1',
    })
  })

  it('prefers citation entity navigation with the active knowledge base and alert context', () => {
    expect(
      citationNavigationTarget(
        { entity_id: 'provider-204', content_id: 'chunk-1' },
        { knowledgeBaseId: 'kb-1', source: 'alert', alertId: 'alert-1' },
      ),
    ).toEqual({ pathname: '/investigation/provider-204', search: 'kb=kb-1&alert=alert-1' })
  })

  it('keeps case, alert, and evidence context on citation entity navigation', () => {
    expect(
      citationNavigationTarget(
        { entity_id: 'provider-204', content_id: 'chunk-1' },
        {
          knowledgeBaseId: 'kb-1',
          source: 'case',
          alertId: 'alert-1',
          caseId: 'case-1',
          evidencePackId: 'evidence-1',
        },
      ),
    ).toEqual({
      pathname: '/investigation/provider-204',
      search: 'kb=kb-1&alert=alert-1&case=case-1&evidence=evidence-1',
    })
  })

  it('keeps document-only alert citations inert instead of falling back to alert context', () => {
    expect(
      citationNavigationTarget(
        { entity_id: null, content_id: 'chunk-1', document_id: 'claims.csv', chunk_index: 1 },
        { knowledgeBaseId: 'kb-1', source: 'alert', alertId: 'alert-1' },
      ),
    ).toBeNull()
  })

  it('keeps document-only case citations inert instead of falling back to case context', () => {
    expect(
      citationNavigationTarget(
        { content_id: 'chunk-1', document_id: 'case-notes.md', chunk_index: 2 },
        { knowledgeBaseId: 'kb-1', source: 'case', caseId: 'case-1' },
      ),
    ).toBeNull()
  })

  it('keeps document-only housing citations inert instead of falling back to housing context', () => {
    expect(
      citationNavigationTarget(
        { content_id: 'chunk-1', document_id: 'housing.pdf', chunk_index: 3 },
        { knowledgeBaseId: 'kb-1', source: 'housing', installationId: 'edwards' },
      ),
    ).toBeNull()
  })

  it('returns null when no citation or context navigation target exists', () => {
    expect(
      citationNavigationTarget(
        { content_id: 'chunk-1' },
        { knowledgeBaseId: null, source: 'entity' },
      ),
    ).toBeNull()
  })
})
