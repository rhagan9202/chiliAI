import type { IngestionSourceType } from '../../lib/ingestion/types'
import { Chip } from '../ui/Chip'
import './ingestion.css'

type SubmitPanelProps = {
  sourceType: IngestionSourceType | null
  canRunIngestion: boolean
  runPending: boolean
  onRunIngestion: () => void
}

function statusLabel({
  sourceType,
  canRunIngestion,
  runPending,
}: Pick<SubmitPanelProps, 'sourceType' | 'canRunIngestion' | 'runPending'>): string {
  if (runPending) {
    return 'Running ingestion'
  }

  if (!sourceType) {
    return 'Select source type'
  }

  if (canRunIngestion) {
    return sourceType === 'documents' ? 'Documents ready' : 'Records ready'
  }

  return sourceType === 'documents' ? 'Select documents' : 'Parse records'
}

export function SubmitPanel({
  sourceType,
  canRunIngestion,
  runPending,
  onRunIngestion,
}: SubmitPanelProps) {
  const label = statusLabel({ sourceType, canRunIngestion, runPending })
  // The chip is the "why is this disabled" text for this control: it names the
  // missing prerequisite, and reads success once nothing is missing.
  const tone = runPending ? 'info' : canRunIngestion ? 'success' : 'warning'

  return (
    <section className="ingestion-submit-panel" aria-labelledby="ingestion-submit-title">
      <div className="ingestion-source-panel__header">
        <h3 id="ingestion-submit-title" className="ingestion-source-panel__title">
          Run ingestion
        </h3>
      </div>

      <div className="ingestion-submit-panel__actions">
        <div className="ingestion-submit-panel__action">
          <button
            aria-busy={runPending}
            className="page-button page-button--primary"
            disabled={!canRunIngestion || runPending}
            type="button"
            onClick={onRunIngestion}
          >
            Run ingestion
          </button>
          <span className="ingestion-submit-panel__status" role={runPending ? 'status' : undefined}>
            <Chip tone={tone} label={label} />
          </span>
        </div>
      </div>
    </section>
  )
}
