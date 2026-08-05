import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { PlaybookResponse } from '../../../api/contracts'
import { PlaybookDetailPanel } from '../PlaybookDetailPanel'

const playbook: PlaybookResponse = {
  id: 'provider_velocity_review',
  title: 'Provider velocity review',
  summary: 'Review unexpected billing velocity.',
  version: 'v2',
  status: 'published',
  evidence_requirements: [
    {
      id: 'claims-history',
      label: 'Claims history',
      description: 'Recent and historical claims for the subject.',
      required: true,
      source_types: ['claims', 'risk_projection'],
    },
  ],
  workflow_steps: [
    {
      id: 'review-peer-context',
      label: 'Review peer context',
      capability_ref: 'peer_stats',
      input_refs: ['claims-history'],
      output_refs: ['peer-review'],
      requires_human_approval: true,
    },
  ],
  rag_prompts: [
    {
      id: 'analyst-summary',
      model_ref: 'default',
      prompt_version: 'v1',
      system_prompt: 'Summarize evidence.',
      user_prompt: 'What changed?',
    },
  ],
  decision_guidance: ['Escalate when peer deviation remains unexplained.'],
}

describe('PlaybookDetailPanel', () => {
  it('shows evidence requirements, workflow steps, RAG prompt labels, and decision guidance', () => {
    render(<PlaybookDetailPanel playbook={playbook} />)

    const panel = screen.getByRole('group', { name: 'Playbook detail' })
    expect(within(panel).getByText('Claims history')).toBeInTheDocument()
    expect(within(panel).getByText('Recent and historical claims for the subject.')).toBeInTheDocument()
    expect(within(panel).getByText('claims, risk_projection')).toBeInTheDocument()
    expect(within(panel).getByText('Review peer context')).toBeInTheDocument()
    expect(within(panel).getByText('peer_stats')).toBeInTheDocument()
    expect(within(panel).getByText('Human approval required')).toBeInTheDocument()
    expect(within(panel).getByText('analyst-summary')).toBeInTheDocument()
    expect(within(panel).getByText('default · v1')).toBeInTheDocument()
    expect(within(panel).getByText('Escalate when peer deviation remains unexplained.')).toBeInTheDocument()
  })
})
