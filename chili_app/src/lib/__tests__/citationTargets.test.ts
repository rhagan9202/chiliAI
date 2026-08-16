import { describe, expect, it } from 'vitest'

import {
  resolveEvidenceCitationTarget,
  resolveRagCitationTarget,
  type EvidenceCitationReference,
} from '../citationTargets'

function reference(overrides: Partial<EvidenceCitationReference>): EvidenceCitationReference {
  return {
    reference_type: 'document',
    reference_id: 'doc-1#evidence:0',
    label: 'Claim note',
    route_target: '/knowledgebases/kb-1/documents/doc-1/preview',
    metadata: {},
    ...overrides,
  }
}

describe('citationTargets', () => {
  it('resolves KB-scoped document provenance to the document inventory preview', () => {
    expect(
      resolveEvidenceCitationTarget({
        knowledgeBaseId: 'kb-1',
        reference: reference({}),
      }),
    ).toEqual({
      kind: 'link',
      label: 'Claim note',
      sourceType: 'document',
      to: '/knowledge-bases/kb-1/data?document=doc-1',
      preview: 'Document preview',
    })
  })

  it('resolves backend entity provenance routes to the investigation cockpit', () => {
    expect(
      resolveEvidenceCitationTarget({
        knowledgeBaseId: 'kb-1',
        reference: reference({
          reference_type: 'risk_factor',
          reference_id: 'provider-1',
          label: 'Provider 1',
          route_target: '/investigation/entities/provider-1?knowledge_base_id=kb-1',
        }),
      }),
    ).toEqual({
      kind: 'link',
      label: 'Provider 1',
      sourceType: 'risk_factor',
      to: '/investigation/provider-1?kb=kb-1',
      preview: 'Investigation cockpit',
    })
  })

  it('resolves policy item provenance to the policy workspace with KB scope', () => {
    expect(
      resolveEvidenceCitationTarget({
        knowledgeBaseId: 'kb-1',
        reference: reference({
          reference_type: 'policy_item',
          reference_id: 'policy-1',
          label: 'LCD policy hit',
          route_target: '/policy/items/policy-1?knowledge_base_id=kb-1',
        }),
      }),
    ).toEqual({
      kind: 'unsupported',
      label: 'LCD policy hit',
      sourceType: 'policy_item',
      reason: 'Policy item selection is not routable yet.',
    })
  })

  it('keeps workflow provenance inert until workflow selection is routable', () => {
    expect(
      resolveEvidenceCitationTarget({
        knowledgeBaseId: 'kb-1',
        reference: reference({
          reference_type: 'workflow',
          reference_id: 'workflow-1',
          label: 'Score-all run',
          route_target: '/workflows/workflow-1',
        }),
      }),
    ).toEqual({
      kind: 'unsupported',
      label: 'Score-all run',
      sourceType: 'workflow',
      reason: 'Workflow run selection is not routable yet.',
    })
  })

  it('keeps correlation provenance inert with a specific reason', () => {
    expect(
      resolveEvidenceCitationTarget({
        knowledgeBaseId: 'kb-1',
        reference: reference({
          reference_type: 'correlation',
          reference_id: 'corr-1',
          label: 'Workflow correlation ID',
          route_target: null,
        }),
      }),
    ).toEqual({
      kind: 'unsupported',
      label: 'Workflow correlation ID',
      sourceType: 'correlation',
      reason: 'Correlation references do not have a source drill-through yet.',
    })
  })

  it('keeps derived model and prompt provenance inert with reason text', () => {
    expect(
      resolveEvidenceCitationTarget({
        knowledgeBaseId: 'kb-1',
        reference: reference({
          reference_type: 'model_version',
          reference_id: 'model-v1',
          label: 'Model version',
          route_target: null,
        }),
      }),
    ).toEqual({
      kind: 'unsupported',
      label: 'Model version',
      sourceType: 'model_version',
      reason: 'Derived model and prompt references do not have a source drill-through yet.',
    })
  })

  it('keeps legacy references without KB scope inert', () => {
    expect(
      resolveEvidenceCitationTarget({
        knowledgeBaseId: null,
        reference: reference({
          reference_type: 'document',
          reference_id: 'doc-1',
          route_target: '/knowledgebases/kb-1/documents/doc-1/preview',
        }),
      }),
    ).toEqual({
      kind: 'unsupported',
      label: 'Claim note',
      sourceType: 'document',
      reason: 'Citation target requires an active knowledge base.',
    })
  })

  it('does not trust unsafe absolute route targets', () => {
    expect(
      resolveEvidenceCitationTarget({
        knowledgeBaseId: 'kb-1',
        reference: reference({
          route_target: 'https://example.test/knowledgebases/kb-1/documents/doc-1/preview',
        }),
      }),
    ).toEqual({
      kind: 'unsupported',
      label: 'Claim note',
      sourceType: 'document',
      reason: 'Citation route target is not a supported app route.',
    })
  })

  it('does not trust protocol-relative route targets', () => {
    expect(
      resolveEvidenceCitationTarget({
        knowledgeBaseId: 'kb-1',
        reference: reference({
          route_target: '//example.test/knowledgebases/kb-1/documents/doc-1/preview',
        }),
      }),
    ).toEqual({
      kind: 'unsupported',
      label: 'Claim note',
      sourceType: 'document',
      reason: 'Citation route target is not a supported app route.',
    })
  })

  it('rejects route targets scoped to another knowledge base', () => {
    expect(
      resolveEvidenceCitationTarget({
        knowledgeBaseId: 'kb-1',
        reference: reference({
          reference_type: 'risk_factor',
          reference_id: 'provider-1',
          label: 'Provider 1',
          route_target: '/investigation/entities/provider-1?knowledge_base_id=kb-other',
        }),
      }),
    ).toEqual({
      kind: 'unsupported',
      label: 'Provider 1',
      sourceType: 'risk_factor',
      reason: 'Citation target is outside the active knowledge base.',
    })
  })

  it('rejects route targets with encoded traversal segments', () => {
    expect(
      resolveEvidenceCitationTarget({
        knowledgeBaseId: 'kb-1',
        reference: reference({
          reference_type: 'risk_factor',
          reference_id: 'provider-1',
          label: 'Provider 1',
          route_target: '/investigation/%2e%2e/provider-1?kb=kb-1',
        }),
      }),
    ).toEqual({
      kind: 'unsupported',
      label: 'Provider 1',
      sourceType: 'risk_factor',
      reason: 'Citation route target is not a supported app route.',
    })
  })

  it('prefers RAG citation entity navigation over document metadata', () => {
    expect(
      resolveRagCitationTarget({
        citation: {
          record_id: 'record-1',
          content_id: 'chunk-1',
          document_id: 'doc-1',
          chunk_index: 3,
          entity_id: 'provider-204',
        },
        context: {
          knowledgeBaseId: 'kb-1',
          source: 'case',
          alertId: 'alert-1',
          caseId: 'case-1',
          evidencePackId: 'evidence-1',
        },
      }),
    ).toEqual({
      kind: 'link',
      label: 'provider-204',
      sourceType: 'entity',
      to: '/investigation/provider-204?kb=kb-1&alert=alert-1&case=case-1&evidence=evidence-1',
      preview: 'Investigation cockpit',
    })
  })

  it('resolves document RAG citations with active KB scope', () => {
    expect(
      resolveRagCitationTarget({
        citation: {
          record_id: 'record-1',
          content_id: 'chunk-1',
          document_id: 'doc-1',
          chunk_index: 3,
        },
        context: { knowledgeBaseId: 'kb-1', source: 'alert', alertId: 'alert-1' },
      }),
    ).toEqual({
      kind: 'link',
      label: 'doc-1',
      sourceType: 'document',
      to: '/knowledge-bases/kb-1/data?document=doc-1&chunk=3',
      preview: 'Document preview',
    })
  })
})
