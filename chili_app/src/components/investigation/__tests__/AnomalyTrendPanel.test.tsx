import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { TimeseriesResponse } from '../../../api/contracts'
import { AnomalyTrendPanel } from '../AnomalyTrendPanel'

const timeseries: TimeseriesResponse = {
  entity_id: 'provider:1',
  metric_name: 'weekly_carrier_billing_self',
  points: [
    { timestamp: '2026-01-05T00:00:00Z', value: 10, label: 'Jan 05', is_anomaly: false },
    { timestamp: '2026-01-12T00:00:00Z', value: 60, label: 'Jan 12', is_anomaly: true },
  ],
  availability_status: 'available',
  unavailable_reason: null,
}

describe('AnomalyTrendPanel', () => {
  it('renders the chart and an anomaly chip per anomalous point', () => {
    render(<AnomalyTrendPanel timeseries={timeseries} unavailableReason={null} />)
    expect(screen.getByText(/JAN 12 ANOMALY/i)).toBeInTheDocument()
  })

  it('renders an empty state with the reason when unavailable', () => {
    render(
      <AnomalyTrendPanel
        timeseries={null}
        unavailableReason="No time series is configured or populated for this entity."
      />,
    )
    expect(
      screen.getByText('No time series is configured or populated for this entity.'),
    ).toBeInTheDocument()
  })

  it('asks for an entity only when none is selected', () => {
    render(<AnomalyTrendPanel entitySelected={false} timeseries={null} unavailableReason={null} />)

    expect(screen.getByText('Select an entity to load its trend.')).toBeInTheDocument()
  })

  it('does not ask for an entity while one is selected', () => {
    // The Signals tab showed "Select an entity to load its trend" *with* an
    // entity selected — the wrong empty state for the state (UXA-305).
    render(<AnomalyTrendPanel entitySelected timeseries={null} unavailableReason={null} />)

    expect(screen.queryByText('Select an entity to load its trend.')).not.toBeInTheDocument()
    expect(
      screen.getByText('No trend has been generated for this entity yet.'),
    ).toBeInTheDocument()
  })
})
