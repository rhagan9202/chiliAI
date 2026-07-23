import type { RiskFactorResponse } from '../../api/contracts'

export interface SignalBandProps {
  factors: RiskFactorResponse[]
}

export function SignalBand({ factors }: SignalBandProps) {
  if (factors.length === 0) {
    return null
  }
  return (
    <div className="callout--ai signal-band" data-testid="signal-band">
      <span className="flag-label" style={{ color: 'var(--c-cyan)' }}>
        ◆ AI ANALYSIS · {factors.length} RISK SIGNAL{factors.length === 1 ? '' : 'S'}
      </span>
      {factors.map((factor) => {
        const magnitude = Math.min(100, Math.round(Math.abs(factor.contribution) * 100))
        const raising = factor.contribution >= 0
        return (
          <div className="signal-band__row" key={factor.factor_name}>
            <div>
              <strong>{factor.factor_name.replace(/_/g, ' ')}</strong>
              <div className="metric-row__label">
                {factor.rationale ?? 'No rationale provided.'}
              </div>
            </div>
            <div className="signal-band__bar" title={`${factor.contribution.toFixed(2)}`}>
              <div
                style={{
                  width: `${magnitude}%`,
                  height: '100%',
                  background: raising ? 'var(--c-red)' : 'var(--c-green)',
                }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}
