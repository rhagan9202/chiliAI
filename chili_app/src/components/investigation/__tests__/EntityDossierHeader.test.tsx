import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { DomainConfig, RiskScoreResponse, RuntimeEntity } from '../../../api/contracts'
import { EntityDossierHeader } from '../EntityDossierHeader'

const config = {
  name: 'medicare_fraud',
  display_name: 'Medicare Fraud Detection',
  entities: [{ name: 'provider', display_label: 'Provider', icon: 'shield', properties: {} }],
  relationships: [],
  ui: {
    display_fields: {
      provider: { title: 'npi', subtitle: 'specialty', chips: ['state'] },
    },
  },
} as unknown as DomainConfig

const entity = {
  id: 'provider:1',
  type: 'provider',
  properties: { npi: '1234567890', specialty: 'Internal Medicine', state: 'TN' },
  metadata: {},
} as unknown as RuntimeEntity

const risk: RiskScoreResponse = {
  entity_id: 'provider:1',
  overall_score: 0.87,
  risk_level: 'high',
  factors: [],
  availability_status: 'available',
  unavailable_reason: null,
}

describe('EntityDossierHeader', () => {
  it('renders identity through domainDisplay and the risk numeral', () => {
    render(
      <EntityDossierHeader
        config={config}
        entity={entity}
        onAskAi={vi.fn()}
        riskScore={risk}
        riskUnavailableReason={null}
      />,
    )
    expect(screen.getByText('1234567890')).toBeInTheDocument()
    expect(screen.getByText('87')).toBeInTheDocument()
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '87')
  })

  it('omits the numeral block and shows the reason when risk is unavailable', () => {
    render(
      <EntityDossierHeader
        config={config}
        entity={entity}
        onAskAi={vi.fn()}
        riskScore={null}
        riskUnavailableReason="No risk profile has been generated for this entity."
      />,
    )
    expect(screen.queryByRole('meter')).not.toBeInTheDocument()
    expect(
      screen.getByText('No risk profile has been generated for this entity.'),
    ).toBeInTheDocument()
  })
})
