import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { useHousingInstallations } from '../api/housing'
import { exportScorecardRun, useScorecardRun } from '../api/scorecards'
import type {
  ScorecardExportFormat,
  ScorecardMetricResponse,
  ScorecardRunResponse,
} from '../api/contracts'
import { showToast } from '../components/common/toastStore'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import { ApiError } from '../lib/apiClient'
import './pages.css'

const HEALTH_TONE: Record<ScorecardRunResponse['overall_health'], 'default' | 'success' | 'warning' | 'danger'> = {
  pass: 'success',
  warn: 'warning',
  fail: 'danger',
  incomplete: 'default',
}

const RUN_STATUS_TONE: Record<ScorecardRunResponse['status'], 'default' | 'success' | 'warning' | 'danger'> = {
  generated: 'success',
  failed: 'danger',
  superseded: 'warning',
}

const COMPLETENESS_LABEL: Record<ScorecardMetricResponse['completeness'], string> = {
  complete: 'complete',
  missing_source: 'source missing',
  stale_source: 'source stale',
  formula_error: 'formula error',
}

const COMPLETENESS_TONE: Record<ScorecardMetricResponse['completeness'], 'default' | 'warning' | 'danger'> = {
  complete: 'default',
  missing_source: 'danger',
  stale_source: 'warning',
  formula_error: 'danger',
}

const HOUSING_CATEGORY_LABEL: Record<ScorecardMetricResponse['housing_category'], string> = {
  UH: 'Unaccompanied housing',
  MFH: 'Military family housing',
  combined: 'Combined portfolio',
}

function formatDate(value: string): string {
  const [datePart] = value.split('T')
  const [year, month, day] = datePart.split('-').map((part) => Number(part))
  if (!year || !month || !day) {
    return value
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(new Date(year, month - 1, day))
}

function formatMetricValue(value: number | null | undefined, unit: string): string {
  if (value == null) {
    return 'n/a'
  }
  if (unit === 'percent') {
    return `${Math.round(value * 100)}%`
  }
  const rendered = Number.isInteger(value)
    ? String(value)
    : value.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return unit ? `${rendered} ${unit}` : rendered
}

function downloadTextFile(filename: string, content: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function MetricRow({ metric }: { metric: ScorecardMetricResponse }) {
  return (
    <li className="scorecard-metric">
      <div className="scorecard-metric__header">
        <div className="scorecard-metric__title">
          <strong>{metric.label}</strong>
          <span className="metric-row__label">{HOUSING_CATEGORY_LABEL[metric.housing_category]}</span>
        </div>
        <div className="scorecard-metric__signals">
          <span className="scorecard-metric__value">{formatMetricValue(metric.value, metric.unit)}</span>
          <Chip label={metric.health} tone={HEALTH_TONE[metric.health]} />
          {metric.completeness !== 'complete' ? (
            <Chip
              label={COMPLETENESS_LABEL[metric.completeness]}
              tone={COMPLETENESS_TONE[metric.completeness]}
            />
          ) : null}
        </div>
      </div>
      {metric.warnings.length > 0 ? (
        <ul aria-label={`Warnings for ${metric.label}`} className="scorecard-metric__warnings">
          {metric.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
      {metric.citations.length > 0 ? (
        <ul aria-label={`Citations for ${metric.label}`} className="scorecard-metric__citations">
          {metric.citations.map((citation) => (
            <li key={citation.citation_id}>
              <span className="scorecard-citation__feed">{citation.feed_name}</span>
              <span className="scorecard-citation__record">
                {citation.record_id}
                {citation.field ? ` · ${citation.field}` : ''}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <span className="scorecard-metric__no-citations">No citations recorded</span>
      )}
      {metric.description ? (
        <details className="scorecard-metric__description">
          <summary>How this metric is computed</summary>
          <p>{metric.description}</p>
        </details>
      ) : null}
    </li>
  )
}

export function ScorecardRunPage() {
  const { runId } = useParams<{ runId: string }>()
  const [searchParams] = useSearchParams()
  const knowledgeBaseId = searchParams.get('kb')
  const runQuery = useScorecardRun(knowledgeBaseId, runId ?? null)
  const installationsQuery = useHousingInstallations()
  const [exporting, setExporting] = useState<ScorecardExportFormat | null>(null)

  if (!knowledgeBaseId) {
    return (
      <EmptyState
        action={
          <Link className="page-button" to="/housing">
            Back to housing dashboard
          </Link>
        }
        description="This scorecard link is missing its knowledge base context (?kb=). Open the run from the housing dashboard so the viewer knows which knowledge base to read."
        title="Missing knowledge base context"
      />
    )
  }

  if (runQuery.isLoading) {
    return <LoadingState label="Loading scorecard run" />
  }

  if (runQuery.isError) {
    if (runQuery.error instanceof ApiError && runQuery.error.status === 404) {
      return (
        <EmptyState
          action={
            <Link className="page-button" to="/housing">
              Back to housing dashboard
            </Link>
          }
          description="No scorecard run with this id exists in the selected knowledge base. It may have been generated against a different knowledge base or removed."
          title="Scorecard run not found"
        />
      )
    }
    return <ErrorState description="The scorecard run could not be loaded from the API." />
  }

  const run = runQuery.data
  if (!run) {
    return <ErrorState description="The scorecard run could not be loaded from the API." />
  }

  const installations = installationsQuery.data?.items ?? []
  const scopeName =
    run.scope_type === 'installation'
      ? installations.find((installation) => installation.installation_id === run.scope_id)?.name ??
        run.scope_id
      : run.scope_id
  const backHref =
    run.scope_type === 'installation'
      ? `/housing?installation=${encodeURIComponent(run.scope_id)}`
      : '/housing'
  const period = `${formatDate(run.period_start)} – ${formatDate(run.period_end)}`

  const handleExport = async (format: ScorecardExportFormat) => {
    if (!runId) {
      return
    }
    setExporting(format)
    try {
      const payload = await exportScorecardRun(knowledgeBaseId, runId, format)
      const extension = payload.format === 'markdown' ? 'md' : 'json'
      const mimeType = payload.format === 'markdown' ? 'text/markdown' : 'application/json'
      downloadTextFile(`scorecard-${payload.run_id}.${extension}`, payload.content, mimeType)
    } catch {
      showToast('error', 'Could not export the scorecard run.')
    } finally {
      setExporting(null)
    }
  }

  return (
    <section className="page-grid">
      <SectionHeader
        actions={
          <div className="page-actions-inline">
            <Link className="page-button page-button--secondary" to={backHref}>
              {run.scope_type === 'installation' ? `Back to ${scopeName}` : 'Back to housing dashboard'}
            </Link>
            <button
              className="page-button"
              disabled={exporting !== null}
              onClick={() => void handleExport('json')}
              type="button"
            >
              {exporting === 'json' ? 'Exporting…' : 'Download JSON'}
            </button>
            <button
              className="page-button"
              disabled={exporting !== null}
              onClick={() => void handleExport('markdown')}
              type="button"
            >
              {exporting === 'markdown' ? 'Exporting…' : 'Download Markdown'}
            </button>
          </div>
        }
        eyebrow="NDAA housing scorecard"
        subtitle={`${scopeName} · ${period}`}
        title={run.template_name}
      />

      {run.status === 'failed' ? (
        <div className="scorecard-banner scorecard-banner--failed" role="alert">
          <strong>This scorecard run failed</strong>
          <span>
            Metric evaluation did not complete. Results below may be missing or partial — regenerate
            the scorecard once the underlying feeds are available.
          </span>
        </div>
      ) : null}
      {run.status === 'superseded' ? (
        <div className="scorecard-banner scorecard-banner--superseded">
          <strong>Superseded run</strong>
          <span>A newer run replaces this scorecard for the same scope and period.</span>
        </div>
      ) : null}

      <Card>
        <section aria-label="Run summary" className="metric-stack">
          <div className="alert-row-card__meta">
            <Chip label={`overall ${run.overall_health}`} tone={HEALTH_TONE[run.overall_health]} />
            <Chip label={run.status} tone={RUN_STATUS_TONE[run.status]} />
          </div>
          <div className="housing-detail-grid">
            <div>
              <span className="metric-row__label">Scope</span>
              <strong>{scopeName}</strong>
            </div>
            <div>
              <span className="metric-row__label">Period</span>
              <strong>{period}</strong>
            </div>
            <div>
              <span className="metric-row__label">Generated</span>
              <strong>{formatDate(run.created_at)}</strong>
            </div>
            <div>
              <span className="metric-row__label">Template</span>
              <strong>{run.template_name}</strong>
            </div>
          </div>
        </section>
      </Card>

      {run.sections.length === 0 ? (
        <EmptyState
          description={
            run.status === 'failed'
              ? 'The failed run recorded no metric sections.'
              : 'This run recorded no metric sections.'
          }
          title="No metrics recorded"
        />
      ) : (
        run.sections.map((section) => (
          <Card key={section.id}>
            <section aria-label={section.label} className="metric-stack">
              <div className="metric-row">
                <strong>{section.label}</strong>
                <Chip
                  label={`${section.metrics.length} ${section.metrics.length === 1 ? 'metric' : 'metrics'}`}
                  tone="info"
                />
              </div>
              <ul className="scorecard-metrics">
                {section.metrics.map((metric) => (
                  <MetricRow key={metric.metric_id} metric={metric} />
                ))}
              </ul>
            </section>
          </Card>
        ))
      )}
    </section>
  )
}
