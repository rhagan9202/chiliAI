import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import type { EvidencePackResponse } from '../../../api/contracts'
import type { Entity, Relationship, SubgraphResult } from '../../../types/api'
import { EvidencePackViewer } from '../EvidencePackViewer'

vi.mock('../GraphCanvas', () => ({
  GraphCanvas: ({ subgraph, testId }: { subgraph: SubgraphResult; testId?: string }) => (
    <div data-testid={testId}>{subgraph.nodes.length} nodes</div>
  ),
}))

function _entity(id: string, type: string): Entity {
  return { id, type, properties: {}, metadata: {}, created_at: '2026-06-01T00:00:00Z', version: 1 }
}

function _relationship(id: string, source: string, target: string): Relationship {
  return {
    id,
    type: 'billed_for',
    source_id: source,
    target_id: target,
    properties: {},
    metadata: {},
    created_at: '2026-06-01T00:00:00Z',
    version: 1,
  }
}

const subgraph: SubgraphResult = {
  nodes: [_entity('provider-1', 'provider'), _entity('claim-1', 'claim'), _entity('beneficiary-1', 'beneficiary')],
  edges: [_relationship('rel-1', 'claim-1', 'provider-1'), _relationship('rel-2', 'claim-1', 'beneficiary-1')],
}

const basePack: EvidencePackResponse = {
  id: 'ev-1',
  alert_id: 'alert-1',
  reasoning: 'Provider billing is materially above peers.',
  created_at: '2026-05-12T09:00:00Z',
  source_documents: ['policy-2026.pdf'],
  confidence: 0.82,
  scores: { overall: 0.82, upcoding: 0.7 },
  subgraph_node_ids: ['provider-1', 'claim-1'],
  subgraph_edge_ids: ['rel-1'],
  items: [
    { source_id: 'provider-1', source_type: 'risk_factor', quote: 'upcoding', rationale: 'High volume.', score: 0.7 },
  ],
  policy_citations: [
    { citation_id: 'c1', title: 'LCD L1234', excerpt: 'Coverage limited to...', source_document_id: 'doc-1' },
  ],
}

function renderViewer(pack: EvidencePackResponse, options?: { entityTypes?: string[] }) {
  return render(
    <MemoryRouter>
      <EvidencePackViewer
        knowledgeBaseId="kb-1"
        pack={pack}
        subgraph={subgraph}
        entityTypes={options?.entityTypes ?? ['provider', 'claim', 'beneficiary']}
      />
    </MemoryRouter>,
  )
}

describe('EvidencePackViewer', () => {
  it('renders reasoning, metrics, items, citations, and the pack subgraph', () => {
    renderViewer(basePack)

    expect(screen.getByText('Provider billing is materially above peers.')).toBeInTheDocument()
    // Labeled so it cannot be confused with the alert's own confidence, and
    // score keys are humanized rather than shown raw (UXA-303).
    expect(screen.getByText('Evidence confidence 82%')).toBeInTheDocument()
    // An explanation with no date and no sources is an unattributed
    // assertion (UXA-405).
    expect(screen.getByText(/^Generated /)).toHaveAttribute(
      'title',
      'May 12, 2026, 09:00 UTC',
    )
    expect(screen.getByText('Drawn from')).toBeInTheDocument()
    expect(screen.getByText('policy-2026.pdf')).toBeInTheDocument()
    expect(screen.getByText('Upcoding 70%')).toBeInTheDocument()
    expect(screen.getByText('High volume.')).toBeInTheDocument()
    expect(screen.getByText('LCD L1234')).toBeInTheDocument()

    // Subgraph is filtered to the pack's node ids (provider-1, claim-1).
    expect(screen.getByTestId('evidence-pack-subgraph')).toHaveTextContent('2 nodes')
  })

  it('falls back to the full neighborhood when no pack node overlaps', () => {
    const detached: EvidencePackResponse = { ...basePack, subgraph_node_ids: ['orphan'] }

    renderViewer(detached, { entityTypes: ['provider'] })

    expect(screen.getByTestId('evidence-pack-subgraph')).toHaveTextContent('3 nodes')
  })

  it('leads with the AI narrative band and renders narrative sections', () => {
    renderViewer({
      ...basePack,
      reasoning: 'The provider shows synchronized anomalies.',
      narrative_sections: [
        { heading: 'Risk Factor', body: 'Self-history anomaly z=4.5.', evidence_refs: ['e-1'] },
      ],
    })
    const narrative = screen.getByTestId('evidence-narrative')
    expect(narrative).toHaveTextContent('AI NARRATIVE')
    expect(narrative).toHaveTextContent('The provider shows synchronized anomalies.')
    expect(screen.getByText('Risk Factor')).toBeInTheDocument()
    expect(screen.getByText('Self-history anomaly z=4.5.')).toBeInTheDocument()
  })

  it('renders attribution bars when the pack carries attribution', () => {
    renderViewer({
      ...basePack,
      attribution: [{ feature_name: 'anomaly_signal', contribution: 0.33, rationale: '' }],
    })
    expect(screen.getByTestId('attribution-bars')).toBeInTheDocument()
  })

  it('omits the attribution section for packs without the field', () => {
    renderViewer(basePack)
    expect(screen.queryByTestId('attribution-bars')).not.toBeInTheDocument()
  })

  it('renders provenance badges and bounded expandable metadata', () => {
    const { container } = renderViewer({
      ...basePack,
      provenance: [
        {
          reference_type: 'risk_score',
          reference_id: 'risk:corr-1:kb-1:provider-1',
          label: 'Overall risk score',
          confidence: 0.82,
          route_target: '/investigation/entities/provider-1?knowledge_base_id=kb-1',
          source_system: 'cms-claims',
          source_version: '2026-08-demo',
          transformation_version: 'peerstats-zscore-v1',
          metadata: {
            overall: 0.82,
            evidence_refs: ['provider-1'],
            empty: null,
            long_value: 'x'.repeat(200),
            long_nested: { too: 'large' },
            hidden_field: 'not shown',
          },
        },
        {
          reference_type: 'document',
          reference_id: 'doc-1#evidence:0',
          label: 'Claim volume spike',
          route_target: '/knowledgebases/kb-1/documents/doc-1/preview',
          metadata: { rationale_snippet: 'High-volume support', rationale_length: 19 },
        },
        {
          reference_type: 'risk_factor',
          reference_id: 'provider-1',
          label: 'Provider risk profile',
          route_target: '/investigation/entities/provider-1?knowledge_base_id=kb-1',
          metadata: {},
        },
      ],
    })

    expect(screen.getByText('Provenance')).toBeInTheDocument()
    expect(screen.getByText('risk score')).toBeInTheDocument()
    expect(screen.getByText('document')).toBeInTheDocument()
    expect(screen.getByText('risk factor')).toBeInTheDocument()
    expect(screen.getByText('3 references')).toBeInTheDocument()
    expect(screen.getByText('Claim volume spike')).toBeInTheDocument()
    expect(screen.getByText('Provider risk profile')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open citation source claim volume spike/i })).toHaveAttribute(
      'href',
      '/knowledge-bases?kb=kb-1&document=doc-1',
    )
    expect(screen.getByRole('link', { name: /open citation source provider risk profile/i })).toHaveAttribute(
      'href',
      '/investigation/provider-1?kb=kb-1',
    )
    expect(screen.getByText('Confidence 82%')).toBeInTheDocument()
    expect(container.querySelector('a[href="/knowledgebases/kb-1/documents/doc-1/preview"]')).toBeNull()
    expect(screen.getByText('/knowledgebases/kb-1/documents/doc-1/preview')).toBeInTheDocument()
    expect(screen.getByText('rationale_snippet')).toBeInTheDocument()
    expect(screen.getByText('High-volume support')).toBeInTheDocument()
    expect(screen.getByText('evidence_refs')).toBeInTheDocument()
    expect(screen.getByText('provider-1')).toBeInTheDocument()
    expect(screen.getByText(`${'x'.repeat(117)}...`)).toBeInTheDocument()
    expect(screen.queryByText('x'.repeat(200))).not.toBeInTheDocument()
    expect(screen.getByText('2 more metadata fields')).toBeInTheDocument()
    expect(container.querySelector('details')?.hasAttribute('open')).toBe(false)
  })
})
