import type {
  HousingInstallationResponse,
  ScorecardRunResponse,
  ScorecardTemplateResponse,
} from '../../api/contracts'
import { Chip } from '../ui/Chip'

type ScorecardReadinessPanelProps = {
  canGenerate: boolean
  generatePending: boolean
  knowledgeBaseName: string | null
  recentRuns: ScorecardRunResponse[]
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

function formatDate(value: string) {
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(new Date(value))
}

export function ScorecardReadinessPanel({
  canGenerate,
  generatePending,
  knowledgeBaseName,
  recentRuns,
  selectedInstallation,
  templates,
  onGenerate,
}: ScorecardReadinessPanelProps) {
  const installationTemplates = templates.filter((template) => template.scope === 'installation')
  const selectedRun = selectedInstallation
    ? recentRuns.find((run) => run.scope_id === selectedInstallation.installation_id)
    : null

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
        <span className="metric-row__label">Recent runs</span>
        <Chip label={String(recentRuns.length)} tone={recentRuns.length > 0 ? 'success' : 'default'} />
      </div>
      {selectedRun ? (
        <div className="housing-scorecard-run">
          <strong>{selectedRun.template_name}</strong>
          <span className="metric-row__label">
            {formatDate(selectedRun.period_start)} - {formatDate(selectedRun.period_end)}
          </span>
          <div className="alert-row-card__meta">
            <Chip label={selectedRun.overall_health} tone={healthTone(selectedRun.overall_health)} />
            <Chip label={selectedRun.status} tone={selectedRun.status === 'generated' ? 'success' : 'warning'} />
          </div>
        </div>
      ) : (
        <div className="housing-scorecard-run">
          <strong>{selectedInstallation?.name ?? 'No installation selected'}</strong>
          <span className="metric-row__label">No recent run</span>
        </div>
      )}
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
