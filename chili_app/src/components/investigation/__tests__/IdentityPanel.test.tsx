import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { CanonicalIdentityDetailResponse } from '../../../api/contracts'
import { IdentityPanel } from '../IdentityPanel'

const detail: CanonicalIdentityDetailResponse = {
  canonical_entity_id: 'provider-204',
  knowledge_base_id: 'kb-live',
  limit: 50,
  offset: 0,
  total: 1,
  links: [
    {
      id: 'identity-link-1',
      knowledge_base_id: 'kb-live',
      canonical_entity_id: 'provider-204',
      source_entity_id: 'source-provider-204',
      relationship_type: 'same_as',
      confidence: 'high',
      score: 0.92,
      review_state: 'steward_review',
      decision_source: 'deterministic_rules',
      source_refs: ['nppes:1234567890', 'beneficiary_mbi:1EG4-TE5-MK73'],
      match_reasons: [
        {
          field: 'npi',
          reason: 'identifier_exact',
          score_contribution: 0.6,
        },
      ],
      decision_history: [
        {
          decision: 'approve_merge',
          actor_user_id: 'analyst-42',
          comment: 'same provider after source review',
          created_at: '2026-08-03T12:30:00Z',
        },
      ],
      created_at: '2026-08-03T12:00:00Z',
      updated_at: '2026-08-03T12:30:00Z',
    },
  ],
}

describe('IdentityPanel', () => {
  it('shows source identity refs, confidence, review state, and decisions', () => {
    render(<IdentityPanel detail={detail} isError={false} isLoading={false} />)

    const panel = screen.getByRole('group', { name: 'Identity resolution' })
    expect(within(panel).getByText('source-provider-204')).toBeInTheDocument()
    expect(within(panel).getByText('high confidence')).toBeInTheDocument()
    expect(within(panel).getByText('steward review')).toBeInTheDocument()
    expect(within(panel).getByText('nppes:1234567890')).toBeInTheDocument()
    expect(within(panel).getByText('approve merge')).toBeInTheDocument()
    expect(within(panel).getByText(/same provider after source review/i)).toBeInTheDocument()
  })

  it('redacts sensitive-looking source references', () => {
    render(<IdentityPanel detail={detail} isError={false} isLoading={false} />)

    const panel = screen.getByRole('group', { name: 'Identity resolution' })
    expect(within(panel).queryByText('beneficiary_mbi:1EG4-TE5-MK73')).not.toBeInTheDocument()
    expect(within(panel).getByText('Restricted ref')).toBeInTheDocument()
  })
})
