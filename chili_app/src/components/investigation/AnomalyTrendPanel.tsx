import type { TimeseriesResponse } from '../../api/contracts'
import { TrendBars } from '../charts/TrendBars'
import { Card } from '../ui/Card'
import { EmptyState } from '../ui/EmptyState'

export interface AnomalyTrendPanelProps {
  timeseries: TimeseriesResponse | null
  unavailableReason: string | null
  /** Whether the workbench currently has an entity loaded. */
  entitySelected?: boolean
}

export function AnomalyTrendPanel({
  timeseries,
  unavailableReason,
  entitySelected = false,
}: AnomalyTrendPanelProps) {
  if (!timeseries) {
    // Without this the panel asked for an entity while one was selected —
    // the wrong empty state for the state (UXA-305).
    const fallback = entitySelected
      ? 'No trend has been generated for this entity yet.'
      : 'Select an entity to load its trend.'
    return (
      <Card>
        <EmptyState description={unavailableReason ?? fallback} title="No time series" />
      </Card>
    )
  }

  const points = timeseries.points

  return (
    <Card>
      <div className="metric-stack">
        <strong>Risk pressure trend</strong>
        <div className="chart-shell">
          <TrendBars
            color="#00d4ff"
            data={points.map((point) => ({ label: point.label, value: Number(point.value.toFixed(2)) }))}
          />
        </div>
        <div className="alert-row-card__meta">
          {points.filter((point) => point.is_anomaly).map((point) => (
            <span className="flag-label" key={point.label} style={{ color: 'var(--c-red)' }}>
              {point.label} anomaly
            </span>
          ))}
        </div>
      </div>
    </Card>
  )
}
