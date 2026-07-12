import type { HousingInstallationResponse } from '../../api/contracts'
import { Card } from '../ui/Card'
import { aggregateInstallations } from './housingFilters'

type HousingSummaryBandProps = {
  /** The FILTERED installation set — every band value follows the filters. */
  installations: HousingInstallationResponse[]
  referenceMode: boolean
}

type SummaryCardProps = {
  label: string
  value: string
}

function SummaryCard({ label, value }: SummaryCardProps) {
  return (
    <Card compact>
      <div className="housing-kpi">
        <span className="metric-row__label">{label}</span>
        <strong>{value}</strong>
      </div>
    </Card>
  )
}

function formatFraction(value: number | null): string {
  return value == null ? 'n/a' : `${Math.round(value * 100)}%`
}

function formatScore(value: number | null): string {
  return value == null ? 'n/a' : value.toFixed(1)
}

function formatRatio(value: number | null): string {
  return value == null ? 'n/a' : value.toFixed(2)
}

/**
 * The single summary band above the map: portfolio counts plus the executive
 * aggregates, all recomputed from the filtered installation set with the
 * backend's weighting semantics (see `aggregateInstallations`). Metrics the
 * subset does not report render an honest "n/a". In reference mode (no live
 * feeds) the band keeps its placeholder cards and fabricates nothing.
 */
export function HousingSummaryBand({ installations, referenceMode }: HousingSummaryBandProps) {
  if (referenceMode) {
    return (
      <div aria-label="Housing portfolio summary" className="housing-kpis" role="group">
        <SummaryCard label="Public locations" value={String(installations.length)} />
        <SummaryCard label="Live reporting" value="0" />
        <SummaryCard label="Health scored" value="0" />
        <SummaryCard label="Scorecards" value="pending" />
      </div>
    )
  }

  const aggregates = aggregateInstallations(installations)
  return (
    <div aria-label="Housing portfolio summary" className="housing-kpis" role="group">
      <SummaryCard
        label="Reporting"
        value={`${aggregates.reportingCount}/${aggregates.totalCount}`}
      />
      <SummaryCard label="Open WOs" value={String(aggregates.openWorkOrders)} />
      <SummaryCard label="Critical" value={String(aggregates.criticalCount)} />
      <SummaryCard label="Occupancy" value={formatFraction(aggregates.occupancyRate)} />
      <SummaryCard label="Condition index" value={formatScore(aggregates.conditionIndex)} />
      <SummaryCard label="Satisfaction" value={formatScore(aggregates.residentSatisfaction)} />
      <SummaryCard label="Overdue WO rate" value={formatFraction(aggregates.overdueWorkOrderRate)} />
      <SummaryCard label="UH supply ratio" value={formatRatio(aggregates.uhSupplyRatio)} />
      <SummaryCard label="MFH supply ratio" value={formatRatio(aggregates.mfhSupplyRatio)} />
    </div>
  )
}
