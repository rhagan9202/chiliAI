import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { EvidencePanel } from '../EvidencePanel'
import type { EvidencePack } from '../../../types/api'

function makePack(overrides: Partial<EvidencePack> = {}): EvidencePack {
  return {
    id: 'ev-1',
    alert_id: 'al-1',
    reasoning: 'Provider billed 30 claims to a single beneficiary in one day.',
    subgraph_nodes: ['p-1', 'b-1'],
    subgraph_edges: ['r-1'],
    confidence: 0.78,
    created_at: '2026-04-26T12:00:00Z',
    scores: { graph_anomaly: 0.91 },
    source_documents: ['doc-7'],
    ...overrides,
  }
}

describe('EvidencePanel', () => {
  it('shows placeholder text when no entity is selected', () => {
    render(
      <EvidencePanel
        entityId={null}
        evidence={[]}
        isLoading={false}
        isError={false}
      />,
    )
    expect(screen.getByText(/select a node/i)).toBeInTheDocument()
    expect(screen.getByText(/not yet implemented/i)).toBeInTheDocument()
  })

  it('shows "no evidence" placeholder when entity is selected but no packs returned', () => {
    render(
      <EvidencePanel
        entityId="e-1"
        evidence={[]}
        isLoading={false}
        isError={false}
      />,
    )
    expect(screen.getByText(/no evidence available/i)).toBeInTheDocument()
  })

  it('renders evidence items with confidence and expands to show reasoning', async () => {
    render(
      <EvidencePanel
        entityId="e-1"
        evidence={[makePack()]}
        isLoading={false}
        isError={false}
      />,
    )
    expect(screen.getByText('78%')).toBeInTheDocument()
    expect(screen.queryByText(/graph_anomaly/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Source documents/i)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /ev-1/i }))
    expect(screen.getByText(/graph_anomaly/)).toBeInTheDocument()
    expect(screen.getByText(/Source documents/i)).toBeInTheDocument()
    expect(screen.getByText(/doc-7/)).toBeInTheDocument()
  })
})
