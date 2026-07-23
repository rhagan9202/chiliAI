import type { FeatureAttributionResponse } from '../../api/contracts'

export interface AttributionBarsProps {
  attribution: FeatureAttributionResponse[]
}

const ROW_COLUMNS = 'minmax(0,1fr) 120px auto'

export function AttributionBars({ attribution }: AttributionBarsProps) {
  if (attribution.length === 0) {
    return null
  }
  const maxMagnitude = Math.max(...attribution.map((item) => Math.abs(item.contribution)), 0.0001)
  const sorted = [...attribution].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  )
  return (
    <div className="signal-band" data-testid="attribution-bars">
      <span className="flag-label">Feature attribution</span>
      {sorted.map((item) => {
        const raising = item.contribution >= 0
        const width = Math.round((Math.abs(item.contribution) / maxMagnitude) * 100)
        const signed = `${raising ? '+' : '−'}${Math.abs(item.contribution).toFixed(2)}`
        return (
          <div
            className="signal-band__row"
            data-testid="attribution-row"
            key={item.feature_name}
            style={{ gridTemplateColumns: ROW_COLUMNS }}
          >
            <div>
              <strong>{item.feature_name.replace(/_/g, ' ')}</strong>
              {item.rationale ? (
                <div className="metric-row__label">{item.rationale}</div>
              ) : null}
            </div>
            <div className="signal-band__bar" title={signed}>
              <div
                style={{
                  width: `${width}%`,
                  height: '100%',
                  background: raising ? 'var(--c-red)' : 'var(--c-green)',
                }}
              />
            </div>
            <span className="flag-label">{signed}</span>
          </div>
        )
      })}
    </div>
  )
}
