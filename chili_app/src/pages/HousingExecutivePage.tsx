import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useHousingInstallations } from '../api/housing'
import { useKnowledgeBases } from '../api/knowledgebases'
import { useScorecardRuns } from '../api/scorecards'
import type {
  HousingInstallationResponse,
  KnowledgeBaseSummaryResponse,
  ScorecardRunResponse,
} from '../api/contracts'
import { HousingFilterStrip } from '../components/housing/HousingFilterStrip'
import {
  commandOptions,
  countInstallationsByStatus,
  EMPTY_HOUSING_FILTERS,
  filterInstallations,
  hasActiveHousingFilters,
  readStatusReasons,
  resolveInstallationRank,
  toggleFilterValue,
  type HousingFilterState,
  type InstallationStatus,
} from '../components/housing/housingFilters'
import { HousingSummaryBand } from '../components/housing/HousingSummaryBand'
import { InstallationHealthMap } from '../components/housing/InstallationHealthMap'
import { InstallationRankingTable } from '../components/housing/InstallationRankingTable'
import type { InstallationBranch } from '../components/housing/installationMapGeometry'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import {
  publicReferenceById,
  publicReferenceInstallations,
  publicReferenceMapPoints,
} from '../data/airForceInstallations'
import { buildRagChatUrl } from '../lib/ragContext'
import './pages.css'

const STATUS_TONE: Record<HousingInstallationResponse['status'], 'default' | 'success' | 'warning' | 'danger'> = {
  ok: 'success',
  watch: 'warning',
  critical: 'danger',
  unknown: 'default',
}

const HEALTH_TONE: Record<ScorecardRunResponse['overall_health'], 'default' | 'success' | 'warning' | 'danger'> = {
  pass: 'success',
  warn: 'warning',
  fail: 'danger',
  incomplete: 'default',
}

function formatPercent(value: number | null | undefined) {
  return value == null ? 'n/a' : `${Math.round(value * 100)}%`
}

function formatRunDate(value: string) {
  const [datePart] = value.split('T')
  const [year, month, day] = datePart.split('-').map((part) => Number(part))
  if (!year || !month || !day) {
    return value
  }
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(
    new Date(year, month - 1, day),
  )
}

/** Latest run per template for one installation, newest first (UH and MFH both surface). */
function latestRunsByTemplate(runs: ScorecardRunResponse[]): ScorecardRunResponse[] {
  const byTemplate = new Map<string, ScorecardRunResponse>()
  for (const run of runs) {
    if (!byTemplate.has(run.template_id)) {
      byTemplate.set(run.template_id, run)
    }
  }
  return [...byTemplate.values()]
}

const LIVE_FEEDS_REQUIRED_REASON =
  'Load UMD, BAH, inventory, market, and demographics feeds before generating NDAA scorecards.'

/**
 * Mirror of the backend housing read model's KB resolution
 * (api/_housing_read_model._resolve_knowledge_base_id): `ready` KBs first
 * (fully built), then still-`active` ones — records-only KBs land rows before
 * any pipeline marks them ready — newest `created_at` within each band, KBs
 * pending cleanup excluded. Keeping the two in lockstep means the KB the page
 * generates scorecards against is the KB the /housing endpoints aggregate.
 */
function selectActiveKnowledgeBase(
  knowledgeBases: KnowledgeBaseSummaryResponse[],
): KnowledgeBaseSummaryResponse | null {
  const candidates = knowledgeBases.filter(
    (kb) => (kb.status === 'ready' || kb.status === 'active') && !kb.pending_cleanup,
  )
  if (candidates.length === 0) {
    return null
  }
  return candidates.reduce((best, kb) => {
    const kbReady = kb.status === 'ready'
    const bestReady = best.status === 'ready'
    if (kbReady !== bestReady) {
      return kbReady ? kb : best
    }
    return kb.created_at > best.created_at ? kb : best
  })
}

export function HousingExecutivePage() {
  const installationsQuery = useHousingInstallations()
  const knowledgeBasesQuery = useKnowledgeBases()
  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const activeKnowledgeBase = selectActiveKnowledgeBase(knowledgeBases)
  // The runs endpoint has no scope filter; pull the KB's run history in one
  // page (500 is the API cap) so per-installation lookups stay client-side.
  const runsQuery = useScorecardRuns(
    activeKnowledgeBase ? { knowledgeBaseId: activeKnowledgeBase.id, limit: 500 } : null,
  )
  const [searchParams, setSearchParams] = useSearchParams()
  const [selectedInstallationId, setSelectedInstallationId] = useState<string | null>(null)
  const [filters, setFilters] = useState<HousingFilterState>(EMPTY_HOUSING_FILTERS)

  if (installationsQuery.isLoading || knowledgeBasesQuery.isLoading) {
    return <LoadingState label="Loading housing portfolio" />
  }

  if (installationsQuery.isError || knowledgeBasesQuery.isError) {
    return <ErrorState description="Housing portfolio data could not be loaded from the API." />
  }

  const installationsPayload = installationsQuery.data
  const liveInstallations = installationsPayload?.items ?? []
  const referenceMode = liveInstallations.length === 0
  const referenceInstallations = referenceMode ? publicReferenceInstallations() : []
  const referenceLookup = referenceMode ? publicReferenceById() : new Map()
  const installations = referenceMode ? referenceInstallations : liveInstallations
  const mapPoints = referenceMode ? publicReferenceMapPoints() : installationsPayload?.map_points ?? []

  const filtersActive = hasActiveHousingFilters(filters)
  const filteredInstallations = filterInstallations(installations, filters)
  const filteredInstallationIds = new Set(
    filteredInstallations.map((installation) => installation.installation_id),
  )
  const filteredMapPoints = mapPoints.filter((point) =>
    filteredInstallationIds.has(point.installation_id),
  )

  const requestedInstallationId = searchParams.get('installation')
  const candidateInstallationId = selectedInstallationId ?? requestedInstallationId
  // Selection resolves against the FILTERED set: if the current selection is
  // filtered out, the detail card falls back to the first visible installation
  // without touching the URL, so clearing the filters restores the original
  // selection. Filtered-out installations are not selectable from the UI.
  const activeInstallationId = filteredInstallations.some(
    (installation) => installation.installation_id === candidateInstallationId,
  )
    ? candidateInstallationId
    : filteredInstallations[0]?.installation_id ?? null
  const selectedInstallation =
    filteredInstallations.find(
      (installation) => installation.installation_id === activeInstallationId,
    ) ?? null
  const selectedReference = selectedInstallation
    ? referenceLookup.get(selectedInstallation.installation_id) ?? null
    : null
  // Status strip and the summary band both mirror the filtered set — the
  // filters drive every aggregate, and the filter strip's aria-live count
  // narrates the subset.
  const statusCounts = countInstallationsByStatus(filteredInstallations)
  const availableCommands = commandOptions(installations)
  const selectedRank = selectedInstallation
    ? resolveInstallationRank(installations, selectedInstallation)
    : null
  const statusReasons = selectedInstallation ? readStatusReasons(selectedInstallation) : []

  const runs = runsQuery.data?.items ?? []
  const sortedRuns = [...runs].sort((left, right) => right.created_at.localeCompare(left.created_at))
  const selectedInstallationRuns = selectedInstallation
    ? sortedRuns.filter((run) => run.scope_id === selectedInstallation.installation_id)
    : []
  const selectedRun = selectedInstallationRuns[0] ?? null
  const installationRunLinks = latestRunsByTemplate(selectedInstallationRuns)
  const ragUrl = selectedInstallation
    ? buildRagChatUrl({
        knowledgeBaseId: activeKnowledgeBase?.id ?? null,
        source: 'housing',
        installationId: selectedInstallation.installation_id,
        scorecardRunId: selectedRun?.id ?? null,
        question: `Summarize housing supply risk for ${selectedInstallation.name}.`,
      })
    : '/rag-chat'

  const handleSelectInstallation = (installationId: string) => {
    setSelectedInstallationId(installationId)
    const nextParams = new URLSearchParams(searchParams)
    nextParams.set('installation', installationId)
    setSearchParams(nextParams)
  }

  const handleToggleStatus = (status: InstallationStatus) => {
    setFilters((current) => ({
      ...current,
      statuses: toggleFilterValue(current.statuses, status),
    }))
  }

  const handleToggleBranch = (branch: InstallationBranch) => {
    setFilters((current) => ({
      ...current,
      branches: toggleFilterValue(current.branches, branch),
    }))
  }

  const handleToggleCommand = (command: string) => {
    setFilters((current) => ({
      ...current,
      commands: toggleFilterValue(current.commands, command),
    }))
  }

  const handleClearFilters = () => {
    setFilters(EMPTY_HOUSING_FILTERS)
  }

  return (
    <section className="page-grid">
      <SectionHeader
        actions={
          <div className="housing-header-actions">
            {referenceMode ? <Chip label="Public installation reference" tone="warning" /> : null}
            <Chip
              label={
                referenceMode
                  ? `${installations.length} public locations`
                  : `${installationsPayload?.total ?? installations.length} installations`
              }
              tone="info"
            />
          </div>
        }
        eyebrow="Department of the Air Force housing"
        subtitle={
          referenceMode
            ? 'Public CONUS base locations are shown until UMD, BAH, inventory, market, and demographics feeds are loaded.'
            : 'Installation status, demand pressure, and scorecard readiness across the housing portfolio.'
        }
        title="Housing Supply Health"
      />

      {referenceMode ? (
        <div className="housing-reference-banner">
          <div>
            <strong>Public installation reference</strong>
            <span>Coordinates from open airport data; live housing health requires ingested Air Force housing feeds.</span>
          </div>
          <Chip label="Live feeds required" tone="warning" />
        </div>
      ) : null}

      <HousingSummaryBand installations={filteredInstallations} referenceMode={referenceMode} />

      <HousingFilterStrip
        commands={availableCommands}
        filters={filters}
        matchCount={filteredInstallations.length}
        onClear={handleClearFilters}
        onToggleBranch={handleToggleBranch}
        onToggleCommand={handleToggleCommand}
        onToggleStatus={handleToggleStatus}
        totalCount={installations.length}
      />

      <div className="housing-operating-picture">
        <div className="housing-map-column">
          <InstallationHealthMap
            installations={filteredInstallations}
            mapPoints={filteredMapPoints}
            onSelectInstallation={handleSelectInstallation}
            referenceMode={referenceMode}
            selectedInstallationId={activeInstallationId}
          />
          <div aria-label="Status counts" className="housing-status-strip" role="group">
            {(['critical', 'watch', 'ok', 'unknown'] as const).map((status) => (
              <div className="metric-row" key={status}>
                <span className="metric-row__label">{status}</span>
                <Chip label={String(statusCounts[status])} tone={STATUS_TONE[status]} />
              </div>
            ))}
          </div>
        </div>

        <Card>
          <section aria-label="Installation detail" className="metric-stack">
            {selectedInstallation ? (
              <>
                <div className="metric-row metric-row--stacked">
                  <strong className="housing-detail-title">{selectedInstallation.name}</strong>
                  <span className="metric-row__label">
                    {referenceMode && selectedReference
                      ? [selectedReference.municipality, selectedReference.state].filter(Boolean).join(' / ')
                      : [selectedInstallation.majcom, selectedInstallation.state].filter(Boolean).join(' / ') || 'Unassigned'}
                  </span>
                </div>
                <div className="alert-row-card__meta">
                  {referenceMode ? (
                    <>
                      <Chip label="public location" tone="default" />
                      <Chip label="health pending" tone="warning" />
                      <Chip label={selectedReference?.sourceIdent ?? 'open data'} tone="info" />
                    </>
                  ) : (
                    <>
                      <Chip label={selectedInstallation.status} tone={STATUS_TONE[selectedInstallation.status]} />
                      <Chip label={`${selectedInstallation.open_work_orders} open WOs`} tone="info" />
                      <Chip label={`${formatPercent(selectedInstallation.occupancy_rate)} occupied`} tone="default" />
                    </>
                  )}
                </div>
                {!referenceMode && selectedRank ? (
                  <span className="housing-detail-rank">
                    #{selectedRank.rank} of {selectedRank.total} reporting by open work orders
                  </span>
                ) : null}
                <div className="housing-detail-grid">
                  <div>
                    <span className="metric-row__label">{referenceMode ? 'Source ident' : 'MAJCOM'}</span>
                    <strong>{referenceMode ? selectedReference?.sourceIdent ?? 'Open data' : selectedInstallation.majcom ?? 'n/a'}</strong>
                  </div>
                  <div>
                    <span className="metric-row__label">State</span>
                    <strong>{selectedInstallation.state ?? 'n/a'}</strong>
                  </div>
                  <div>
                    <span className="metric-row__label">{referenceMode ? 'Live feed' : 'Open work orders'}</span>
                    <strong>{referenceMode ? 'Not loaded' : selectedInstallation.open_work_orders}</strong>
                  </div>
                  <div>
                    <span className="metric-row__label">{referenceMode ? 'Housing KPIs' : 'Occupancy'}</span>
                    <strong>{referenceMode ? 'Pending' : formatPercent(selectedInstallation.occupancy_rate)}</strong>
                  </div>
                </div>
                {!referenceMode ? (
                  <div className="housing-status-reasons">
                    <strong>Why this status</strong>
                    {statusReasons.length > 0 ? (
                      <ul>
                        {statusReasons.map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                      </ul>
                    ) : (
                      <span>No status drivers reported for this period.</span>
                    )}
                  </div>
                ) : null}
                {!referenceMode && activeKnowledgeBase ? (
                  <div className="housing-detail-runs">
                    <strong>Scorecards</strong>
                    {installationRunLinks.length > 0 ? (
                      <ul className="housing-run-links">
                        {installationRunLinks.map((run) => (
                          <li key={run.id}>
                            <Link
                              aria-label={`View ${run.template_name} scorecard for ${selectedInstallation.name}, overall ${run.overall_health}`}
                              className="housing-run-link"
                              to={`/scorecards/${encodeURIComponent(run.id)}?kb=${encodeURIComponent(activeKnowledgeBase.id)}`}
                            >
                              <span className="housing-run-link__scope">
                                <strong>{run.template_name}</strong>
                                <span className="metric-row__label">
                                  {formatRunDate(run.period_start)} - {formatRunDate(run.period_end)}
                                </span>
                              </span>
                              <Chip label={run.overall_health} tone={HEALTH_TONE[run.overall_health]} />
                            </Link>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <span className="metric-row__label">No scorecard runs for this installation yet.</span>
                    )}
                  </div>
                ) : null}
                {referenceMode ? (
                  <div className="housing-scorecard-reason">
                    <strong>Live feeds required</strong>
                    <span>{LIVE_FEEDS_REQUIRED_REASON}</span>
                  </div>
                ) : (
                  <Link className="page-button housing-rag-link" to={ragUrl}>
                    Ask AI about {selectedInstallation.name}
                  </Link>
                )}
              </>
            ) : (
              <EmptyState
                description={
                  filtersActive
                    ? 'No installations match the active filters. Clear the filters to restore the full portfolio.'
                    : 'No installation rows are available for the selected period.'
                }
                title={filtersActive ? 'No matching installations' : 'No installation selected'}
              />
            )}
          </section>
        </Card>
      </div>

      <Card>
        <div className="metric-stack">
          <div className="metric-row">
            <strong>Installation ranking</strong>
            <Chip label={`${filteredInstallations.length} rows`} tone="info" />
          </div>
          {filteredInstallations.length === 0 && filtersActive ? (
            <EmptyState
              description="No installations match the active filters."
              title="No matching installations"
            />
          ) : (
            <InstallationRankingTable
              installations={filteredInstallations}
              onSelectInstallation={handleSelectInstallation}
              referenceMode={referenceMode}
              selectedInstallationId={activeInstallationId}
            />
          )}
        </div>
      </Card>
    </section>
  )
}
