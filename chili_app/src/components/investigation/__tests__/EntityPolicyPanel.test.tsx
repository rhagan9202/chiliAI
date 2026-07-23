import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { PolicyItemSummaryResponse } from '../../../api/contracts'

const items: PolicyItemSummaryResponse[] = [
  {
    id: 'pi-1',
    knowledge_base_id: 'kb-1',
    rule_id: 'rule-1',
    rule_pack_id: 'pack-1',
    title: 'Inpatient billing limit exceeded',
    severity: 'critical',
    status: 'open',
    target_kind: 'entity',
    target_ref: 'provider:1',
    updated_at: '2026-07-20T00:00:00Z',
  },
  {
    id: 'pi-2',
    knowledge_base_id: 'kb-1',
    rule_id: 'rule-2',
    rule_pack_id: 'pack-1',
    title: 'Unrelated metric item',
    severity: 'medium',
    status: 'open',
    target_kind: 'metric',
    target_ref: 'weekly_carrier_billing',
    updated_at: '2026-07-20T00:00:00Z',
  },
]

vi.mock('../../../api/policy', () => ({
  usePolicyItems: () => ({ data: { items }, isLoading: false, isError: false }),
}))

import { EntityPolicyPanel } from '../EntityPolicyPanel'
import { policyItemsForTarget } from '../policyTargets'
import { MemoryRouter } from 'react-router-dom'

describe('policyItemsForTarget', () => {
  it('filters by target kind and ref', () => {
    expect(policyItemsForTarget(items, 'entity', 'provider:1')).toHaveLength(1)
    expect(policyItemsForTarget(items, 'entity', 'provider:2')).toHaveLength(0)
  })
})

describe('EntityPolicyPanel', () => {
  it('renders matching items with the critical callout treatment', () => {
    render(
      <MemoryRouter>
        <EntityPolicyPanel knowledgeBaseId="kb-1" targetKind="entity" targetRef="provider:1" />
      </MemoryRouter>,
    )
    expect(screen.getByText('Inpatient billing limit exceeded')).toBeInTheDocument()
    expect(screen.getByText(/POLICY SIGNAL/)).toBeInTheDocument()
    expect(screen.queryByText('Unrelated metric item')).not.toBeInTheDocument()
  })
})
