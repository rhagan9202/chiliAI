import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { RiskFactorResponse } from '../../../api/contracts'
import { SignalBand } from '../SignalBand'

const factors: RiskFactorResponse[] = [
  {
    factor_name: 'timeseries_anomaly:weekly_carrier_billing_self',
    contribution: 0.4,
    rationale: 'self-history anomaly z=4.5',
  },
  { factor_name: 'weekly_carrier_billing', contribution: 0.0, rationale: 'z=-0.2 vs peers' },
]

describe('SignalBand', () => {
  it('announces the signal count in the AI voice and lists every factor', () => {
    render(<SignalBand factors={factors} />)
    expect(screen.getByText(/AI ANALYSIS · 2 RISK SIGNALS/)).toBeInTheDocument()
    expect(screen.getByText('timeseries anomaly:weekly carrier billing self')).toBeInTheDocument()
    expect(screen.getByText('self-history anomaly z=4.5')).toBeInTheDocument()
  })

  it('renders nothing for an empty factor list', () => {
    const { container } = render(<SignalBand factors={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
