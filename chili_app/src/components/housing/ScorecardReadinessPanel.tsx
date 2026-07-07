import { Link } from 'react-router-dom'

import type {
  HousingInstallationResponse,
  ScorecardRunResponse,
  ScorecardTemplateResponse,
} from '../../api/contracts'
import { Chip } from '../ui/Chip'

type ScorecardReadinessPanelProps = {
  canGenerate: boolean
  generatePending: boolean
  generationUnavailableReason?: string | null
  knowledgeBaseId?: string | null
  knowledgeBaseName: string | null
  recentRuns: ScorecardRunResponse[]
  /**
   * Exact run count from the list response's `total` — the fetched page is
   * capped (API limit 500), so `recentRuns.length` can understate it.
   */
  runsTotal?: number | null
  scopeNames?: ReadonlyMap<string, string>
  selectedInstallation: HousingInstallationResponse | null
  templates: ScorecardTemplateResponse[]
  onGenerate: () => void
}

function healthTone(health: ScorecardRunResponse['overall_health']) {
  switch (health) {
    case 'pass':
      return 'success' as const
    case 'warn':
      return 'warning' as const
    case 'fail':
      return 'danger' as const
    case 'incomplete':
      return 'default' as const
  }
}

function runStatusTone(status: ScorecardRunResponse['status']) {
  switch (status) {
    case 'generated':
      return 'success' as const
    case 'failed':
      return 'danger' as const
    case 'superseded':
      return 'warning' as const
  }
}

function formatDate(value: string) {
  const [datePart] = value.split('T')
  const [year, month, day] = datePart.split('-').map((part) => Number(part))
  if (!year || !month || !day) {
    return value
  }
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(
    new Date(year, month - 1, day),
  )
}

function runViewerHref(run: ScorecardRunResponse, knowledgeBaseId: string) {
  return `/scorecards/${encodeURIComponent(run.id)}?kb=${encodeURIComponent(knowledgeBaseId)}`
}

export function ScorecardReadinessPanel({
  canGenerate,
  generatePending,
  generationUnavailableReason = null,
  knowledgeBaseId = null,
  knowledgeBaseName,
  recentRuns,
  runsTotal = null,
  scopeNames,
  selectedInstallation,
  templates,
  onGenerate,
}: ScorecardReadinessPanelProps) {
  const installationTemplates = templates.filter((template) => template.scope === 'installation')
  const generatedRunCount = runsTotal ?? recentRuns.length
  const sortedRuns = [...recentRuns].sort((left, right) =>
    right.created_at.localeCompare(left.created_at),
  )
  const selectedRun = selectedInstallation
    ? sortedRuns.find((run) => run.scope_id === selectedInstallation.installation_id)
    : null
  const latestRuns = sortedRuns.slice(0, 3)

  const selectedRunBody = selectedRun ? (
    <>
      <strong>{selectedRun.template_name}</strong>
      <span className="metric-row__label">
        {formatDate(selectedRun.period_start)} - {formatDate(selectedRun.period_end)}
      </span>
      <div className="alert-row-card__meta">
        <Chip label={selectedRun.overall_health} tone={healthTone(selectedRun.overall_health)} />
        <Chip label={selectedRun.status} tone={runStatusTone(selectedRun.status)} />
      </div>
    </>
  ) : null

  return (
    <div className="metric-stack">
      <div className="metric-row">
        <span className="metric-row__label">Ready KB</span>
        <strong>{knowledgeBaseName ?? 'Unavailable'}</strong>
      </div>
      <div className="metric-row">
        <span className="metric-row__label">Templates</span>
        <Chip label={String(installationTemplates.length)} tone={installationTemplates.length > 0 ? 'info' : 'default'} />
      </div>
      <div className="metric-row">
        <span className="metric-row__label">Runs generated</span>
        <Chip label={String(generatedRunCount)} tone={generatedRunCount > 0 ? 'success' : 'default'} />
      </div>
      {selectedRun && selectedRunBody ? (
        knowledgeBaseId ? (
          <Link
            aria-label={`View ${selectedRun.template_name} scorecard run for ${
              selectedInstallation?.name ?? selectedRun.scope_id
            }`}
            className="housing-scorecard-run housing-scorecard-run--link"
            to={runViewerHref(selectedRun, knowledgeBaseId)}
          >
            {selectedRunBody}
            <span className="housing-run-link__hint">View scorecard</span>
          </Link>
        ) : (
          <div className="housing-scorecard-run">{selectedRunBody}</div>
        )
      ) : (
        <div className="housing-scorecard-run">
          <strong>{selectedInstallation?.name ?? 'No installation selected'}</strong>
          <span className="metric-row__label">No recent run</span>
        </div>
      )}
      {latestRuns.length > 0 ? (
        <div className="housing-recent-runs">
          <span className="metric-row__label">Recent runs</span>
          <ul className="housing-run-links">
            {latestRuns.map((run) => {
              const scopeName = scopeNames?.get(run.scope_id) ?? run.scope_id
              const body = (
                <>
                  <span className="housing-run-link__scope">
                    <strong>{scopeName}</strong>
                    <span className="metric-row__label">
                      {run.template_name} · {formatDate(run.created_at)}
                    </span>
                  </span>
                  <Chip label={run.overall_health} tone={healthTone(run.overall_health)} />
                </>
              )
              return (
                <li key={run.id}>
                  {knowledgeBaseId ? (
                    <Link
                      aria-label={`View ${run.template_name} scorecard run for ${scopeName}, overall ${run.overall_health}`}
                      className="housing-run-link"
                      to={runViewerHref(run, knowledgeBaseId)}
                    >
                      {body}
                    </Link>
                  ) : (
                    <span className="housing-run-link housing-run-link--static">{body}</span>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}
      {generationUnavailableReason ? (
        <div className="housing-scorecard-reason">
          <strong>Live feeds required</strong>
          <span>{generationUnavailableReason}</span>
        </div>
      ) : null}
      <button
        className="page-button"
        disabled={!canGenerate || generatePending}
        onClick={onGenerate}
        type="button"
      >
        {generatePending ? 'Generating' : 'Generate scorecard'}
      </button>
    </div>
  )
}
