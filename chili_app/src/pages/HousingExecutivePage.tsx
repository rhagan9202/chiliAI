import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useHousingInstallations, useHousingOverview } from '../api/housing'
import { useKnowledgeBases } from '../api/knowledgebases'
import { useGenerateScorecardRun, useScorecardRuns, useScorecardTemplates } from '../api/scorecards'
import type {
  HousingExecutiveKpiResponse,
  HousingInstallationResponse,
  ScorecardTemplateResponse,
} from '../api/contracts'
import { showToast } from '../components/common/toastStore'
import { InstallationHealthMap } from '../components/housing/InstallationHealthMap'
import { InstallationRankingTable } from '../components/housing/InstallationRankingTable'
import { ScorecardReadinessPanel } from '../components/housing/ScorecardReadinessPanel'
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

type StatusCounts = Record<HousingInstallationResponse['status'], number>

const STATUS_TONE: Record<HousingInstallationResponse['status'], 'default' | 'success' | 'warning' | 'danger'> = {
  ok: 'success',
  watch: 'warning',
  critical: 'danger',
  unknown: 'default',
}

function formatPercent(value: number | null | undefined) {
  return value == null ? 'n/a' : `${Math.round(value * 100)}%`
}

function formatKpiValue(kpi: HousingExecutiveKpiResponse) {
  if (kpi.value == null) {
    return 'n/a'
  }
  if (kpi.unit === 'percent') {
    return `${Math.round(kpi.value * 100)}%`
  }
  return String(kpi.value)
}

function todayDate() {
  return new Date().toISOString().slice(0, 10)
}

function selectInstallationTemplate(templates: ScorecardTemplateResponse[]) {
  return templates.find((template) => template.scope === 'installation') ?? null
}

const LIVE_FEEDS_REQUIRED_REASON =
  'Load UMD, BAH, inventory, market, and demographics feeds before generating NDAA scorecards.'

export function HousingExecutivePage() {
  const overviewQuery = useHousingOverview()
  const installationsQuery = useHousingInstallations()
  const knowledgeBasesQuery = useKnowledgeBases()
  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const activeKnowledgeBase = knowledgeBases.find((kb) => kb.status === 'ready') ?? null
  const templatesQuery = useScorecardTemplates()
  const runsQuery = useScorecardRuns(
    activeKnowledgeBase ? { knowledgeBaseId: activeKnowledgeBase.id, limit: 5 } : null,
  )
  const generateScorecard = useGenerateScorecardRun()
  const [searchParams, setSearchParams] = useSearchParams()
  const [selectedInstallationId, setSelectedInstallationId] = useState<string | null>(null)

  if (overviewQuery.isLoading || installationsQuery.isLoading || knowledgeBasesQuery.isLoading) {
    return <LoadingState label="Loading housing portfolio" />
  }

  if (overviewQuery.isError || installationsQuery.isError || knowledgeBasesQuery.isError) {
    return <ErrorState description="Housing portfolio data could not be loaded from the API." />
  }

  const overview = overviewQuery.data
  const installationsPayload = installationsQuery.data
  const liveInstallations = installationsPayload?.items ?? []
  const referenceMode = liveInstallations.length === 0
  const referenceInstallations = referenceMode ? publicReferenceInstallations() : []
  const referenceLookup = referenceMode ? publicReferenceById() : new Map()
  const installations = referenceMode ? referenceInstallations : liveInstallations
  const mapPoints = referenceMode ? publicReferenceMapPoints() : installationsPayload?.map_points ?? []
  const requestedInstallationId = searchParams.get('installation')
  const candidateInstallationId = selectedInstallationId ?? requestedInstallationId
  const activeInstallationId = installations.some(
    (installation) => installation.installation_id === candidateInstallationId,
  )
    ? candidateInstallationId
    : installations[0]?.installation_id ?? null
  const selectedInstallation =
    installations.find((installation) => installation.installation_id === activeInstallationId) ?? null
  const selectedReference = selectedInstallation
    ? referenceLookup.get(selectedInstallation.installation_id) ?? null
    : null
  const statusCounts = installations.reduce<StatusCounts>(
    (counts, installation) => ({
      ...counts,
      [installation.status]: counts[installation.status] + 1,
    }),
    { ok: 0, watch: 0, critical: 0, unknown: 0 },
  )
  const templates = templatesQuery.data?.items ?? []
  const runs = runsQuery.data?.items ?? []
  const installationTemplate = selectInstallationTemplate(templates)
  const selectedRun = selectedInstallation
    ? runs.find((run) => run.scope_id === selectedInstallation.installation_id) ?? null
    : null
  const periodStart = overview?.period_start ?? installationsPayload?.period_start ?? todayDate()
  const periodEnd = overview?.period_end ?? installationsPayload?.period_end ?? todayDate()
  const canGenerateScorecard = Boolean(
    !referenceMode && activeKnowledgeBase && selectedInstallation && installationTemplate && periodStart && periodEnd,
  )
  const generationUnavailableReason = referenceMode ? LIVE_FEEDS_REQUIRED_REASON : null
  const ragUrl = selectedInstallation
    ? buildRagChatUrl({
        knowledgeBaseId: activeKnowledgeBase?.id ?? null,
        source: 'housing',
        installationId: selectedInstallation.installation_id,
        scorecardRunId: selectedRun?.id ?? null,
        question: `Summarize housing supply risk for ${selectedInstallation.name}.`,
      })
    : '/rag-chat'

  const handleGenerateScorecard = () => {
    if (!activeKnowledgeBase || !selectedInstallation || !installationTemplate) {
      return
    }

    generateScorecard.mutate(
      {
        knowledge_base_id: activeKnowledgeBase.id,
        template_id: installationTemplate.id,
        scope_type: installationTemplate.scope,
        scope_id: selectedInstallation.installation_id,
        period_start: periodStart,
        period_end: periodEnd,
      },
      {
        onSuccess: () => showToast('success', 'Scorecard generation queued.'),
        onError: () => showToast('error', 'Could not generate the scorecard.'),
      },
    )
  }

  const handleSelectInstallation = (installationId: string) => {
    setSelectedInstallationId(installationId)
    const nextParams = new URLSearchParams(searchParams)
    nextParams.set('installation', installationId)
    setSearchParams(nextParams)
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

      <div className="housing-kpis">
        <Card compact>
          <div className="housing-kpi">
            <span className="metric-row__label">{referenceMode ? 'Public locations' : 'Reporting'}</span>
            <strong>
              {referenceMode
                ? installations.length
                : `${overview?.portfolio_summary?.installations_reporting ?? installations.length}/${
                    overview?.portfolio_summary?.total_installations ?? installationsPayload?.total ?? installations.length
                  }`}
            </strong>
          </div>
        </Card>
        <Card compact>
          <div className="housing-kpi">
            <span className="metric-row__label">{referenceMode ? 'Live reporting' : 'Open WOs'}</span>
            <strong>{referenceMode ? '0' : overview?.portfolio_summary?.open_work_orders ?? 0}</strong>
          </div>
        </Card>
        <Card compact>
          <div className="housing-kpi">
            <span className="metric-row__label">{referenceMode ? 'Health scored' : 'Occupancy'}</span>
            <strong>{referenceMode ? '0' : formatPercent(overview?.portfolio_summary?.occupancy_rate)}</strong>
          </div>
        </Card>
        <Card compact>
          <div className="housing-kpi">
            <span className="metric-row__label">{referenceMode ? 'Scorecards' : 'Critical'}</span>
            <strong>{referenceMode ? 'pending' : statusCounts.critical}</strong>
          </div>
        </Card>
      </div>

      <div className="housing-operating-picture">
        <div className="housing-map-column">
          <InstallationHealthMap
            installations={installations}
            mapPoints={mapPoints}
            onSelectInstallation={handleSelectInstallation}
            referenceMode={referenceMode}
            selectedInstallationId={activeInstallationId}
          />
          <div className="housing-status-strip">
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
              <EmptyState description="No installation rows are available for the selected period." title="No installation selected" />
            )}
          </section>
        </Card>
      </div>

      <div className="housing-lower-grid">
        <Card>
          <div className="metric-stack">
            <div className="metric-row">
              <strong>Installation ranking</strong>
              <Chip label={`${installations.length} rows`} tone="info" />
            </div>
            <InstallationRankingTable
              installations={installations}
              onSelectInstallation={handleSelectInstallation}
              referenceMode={referenceMode}
              selectedInstallationId={activeInstallationId}
            />
          </div>
        </Card>

        <Card>
          <ScorecardReadinessPanel
            canGenerate={canGenerateScorecard}
            generatePending={generateScorecard.isPending}
            generationUnavailableReason={generationUnavailableReason}
            knowledgeBaseName={referenceMode ? 'Live evidence pending' : activeKnowledgeBase?.name ?? null}
            onGenerate={handleGenerateScorecard}
            recentRuns={runs}
            selectedInstallation={selectedInstallation}
            templates={templates}
          />
        </Card>
      </div>

      {overview?.executive_kpis.length ? (
        <div className="housing-executive-kpis">
          {overview.executive_kpis.map((kpi) => (
            <div className="metric-row" key={kpi.label}>
              <span className="metric-row__label">{kpi.label}</span>
              <strong>{formatKpiValue(kpi)}</strong>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}
