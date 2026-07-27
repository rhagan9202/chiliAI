import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { DomainConfig, RiskScoreResponse, RuntimeEntity } from '../../../api/contracts'
import { EntityDossierHeader } from '../EntityDossierHeader'

const config = {
  name: 'medicare_fraud',
  display_name: 'Medicare Fraud Detection',
  entities: [
    {
      name: 'provider',
      display_label: 'Provider',
      icon: 'shield',
      properties: {
        npi: { type: 'string', display: 'NPI' },
        specialty: { type: 'string', display: 'Specialty' },
        state: { type: 'string', display: 'Practice State' },
        organization_name: { type: 'string', display: 'Organization Name' },
        enumeration_date: { type: 'date', display: 'Enumeration Date' },
      },
    },
  ],
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
  properties: {
    npi: '1234567890',
    specialty: 'Internal Medicine',
    state: 'TN',
    organization_name: 'Redwood DME Group',
    enumeration_date: '2020-04-02',
  },
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

  it('labels properties from the domain configuration instead of showing raw keys', () => {
    render(
      <EntityDossierHeader
        config={config}
        entity={entity}
        onAskAi={vi.fn()}
        riskScore={risk}
        riskUnavailableReason={null}
      />,
    )

    expect(screen.getByText('Practice State')).toBeInTheDocument()
    expect(screen.queryByText(/state:/i)).not.toBeInTheDocument()
  })

  it('shows only the configured chip fields until the rest are asked for', () => {
    render(
      <EntityDossierHeader
        config={config}
        entity={entity}
        onAskAi={vi.fn()}
        riskScore={risk}
        riskUnavailableReason={null}
      />,
    )

    expect(screen.getByText('TN')).toBeInTheDocument()
    expect(screen.queryByText('Redwood DME Group')).not.toBeInTheDocument()
  })

  it('reveals every remaining property behind a labeled control', async () => {
    render(
      <EntityDossierHeader
        config={config}
        entity={entity}
        onAskAi={vi.fn()}
        riskScore={risk}
        riskUnavailableReason={null}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Show all 3 properties' }))

    expect(screen.getByText('Redwood DME Group')).toBeInTheDocument()
    // Formatted by its configured `date` type, not echoed as an ISO string.
    expect(screen.getByText('Apr 2, 2020')).toBeInTheDocument()
  })

  it('does not offer the control when nothing is hidden', () => {
    const sparse = {
      ...entity,
      properties: { npi: '1234567890', specialty: 'Internal Medicine', state: 'TN' },
    } as unknown as RuntimeEntity

    render(
      <EntityDossierHeader
        config={config}
        entity={sparse}
        onAskAi={vi.fn()}
        riskScore={risk}
        riskUnavailableReason={null}
      />,
    )

    expect(screen.queryByRole('button', { name: /show all/i })).not.toBeInTheDocument()
  })
})
