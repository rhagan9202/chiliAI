import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { FeatureAttributionResponse } from '../../../api/contracts'
import { AttributionBars } from '../AttributionBars'

const attribution: FeatureAttributionResponse[] = [
  { feature_name: 'peer_deviation', contribution: -0.08, rationale: '' },
  { feature_name: 'anomaly_signal', contribution: 0.33, rationale: 'SHAP attribution' },
]

describe('AttributionBars', () => {
  it('sorts by |contribution| descending and signs the labels', () => {
    render(<AttributionBars attribution={attribution} />)
    const rows = screen.getAllByTestId('attribution-row')
    expect(rows[0]).toHaveTextContent('anomaly signal')
    expect(rows[0]).toHaveTextContent('+0.33')
    expect(rows[1]).toHaveTextContent('−0.08')
  })

  it('renders nothing when attribution is empty', () => {
    const { container } = render(<AttributionBars attribution={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
