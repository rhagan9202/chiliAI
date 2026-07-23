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

  it('renders signed bar fill matching |contribution| and colors by sign', () => {
    const signedFactors: RiskFactorResponse[] = [
      { factor_name: 'risk_raising_factor', contribution: 0.4, rationale: 'raises risk' },
      { factor_name: 'risk_lowering_factor', contribution: -0.25, rationale: 'lowers risk' },
    ]
    const { container } = render(<SignalBand factors={signedFactors} />)
    const rows = container.querySelectorAll('.signal-band__row')
    expect(rows).toHaveLength(2)

    const positiveFill = rows[0].querySelector('.signal-band__bar > div')
    expect(positiveFill).toHaveStyle({ width: '40%', background: 'var(--c-red)' })

    const negativeFill = rows[1].querySelector('.signal-band__bar > div')
    expect(negativeFill).toHaveStyle({ width: '25%', background: 'var(--c-green)' })
  })
})
