import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { EntityDetailPanel } from '../EntityDetailPanel'
import type { Entity } from '../../../types/api'

function makeEntity(): Entity {
  return {
    id: 'entity-99',
    type: 'Provider',
    properties: {
      npi: '1234567890',
      name: 'Acme Clinic',
      risk_score: 0.85,
      community_id: 'C-7',
    },
    metadata: {},
    created_at: '2026-04-25T10:00:00Z',
    updated_at: '2026-04-26T11:00:00Z',
    version: 3,
  }
}

describe('EntityDetailPanel', () => {
  it('renders placeholder when no entity is selected', () => {
    render(
      <EntityDetailPanel
        entity={null}
        isLoading={false}
        isError={false}
      />,
    )
    expect(screen.getByText(/select a node in the graph/i)).toBeInTheDocument()
  })

  it('renders entity properties, risk score, community id, and timestamps', () => {
    render(
      <EntityDetailPanel
        entity={makeEntity()}
        isLoading={false}
        isError={false}
      />,
    )
    expect(screen.getByText('Provider')).toBeInTheDocument()
    expect(screen.getByText('entity-99')).toBeInTheDocument()
    expect(screen.getByText('85%')).toBeInTheDocument()
    expect(screen.getByText('C-7')).toBeInTheDocument()
    expect(screen.getByText('Acme Clinic')).toBeInTheDocument()
    expect(screen.getByText('1234567890')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('toggles collapse state when the toggle button is clicked', async () => {
    render(
      <EntityDetailPanel
        entity={makeEntity()}
        isLoading={false}
        isError={false}
      />,
    )
    const toggle = screen.getByRole('button', { name: /collapse/i })
    expect(screen.getByText('Acme Clinic')).toBeInTheDocument()
    await userEvent.click(toggle)
    expect(screen.queryByText('Acme Clinic')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /expand/i }))
    expect(screen.getByText('Acme Clinic')).toBeInTheDocument()
  })
})
