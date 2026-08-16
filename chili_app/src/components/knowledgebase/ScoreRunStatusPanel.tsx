import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import { formatRelativeTime } from '../status/formatters'
import type { ScoreRunDetailResponse, ScoreRunStatus } from '../../api/contracts'

type ScoreRunStatusPanelProps = {
  detail: ScoreRunDetailResponse | null
  disabled?: boolean
  error?: string | null
  loading?: boolean
  onCancel: () => void
  onReplay: () => void
  onStart: () => void
  pendingAction?: 'cancel' | 'replay' | 'start' | null
  startDisabled?: boolean
  /** Why Start is unavailable. Rendered as visible text, never a tooltip. */
  startReason?: string | null
}

const statusCopy: Record<ScoreRunStatus, { label: string; tone: 'info' | 'success' | 'danger' | 'warning' | 'default' }> = {
  queued: { label: 'Queued', tone: 'info' },
  running: { label: 'Running', tone: 'info' },
  completed: { label: 'Completed', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
  canceled: { label: 'Canceled', tone: 'warning' },
  replayed: { label: 'Replayed', tone: 'default' },
}

function canCancel(status: ScoreRunStatus | null): boolean {
  return status === 'queued' || status === 'running'
}

function canReplay(status: ScoreRunStatus | null): boolean {
  return status === 'failed' || status === 'canceled'
}

export function ScoreRunStatusPanel({
  detail,
  disabled = false,
  error,
  loading = false,
  onCancel,
  onReplay,
  onStart,
  pendingAction = null,
  startDisabled = false,
  startReason = null,
}: ScoreRunStatusPanelProps) {
  const run = detail?.run ?? null
  // Read off the same optional `detail` as `run`, so the batch list does not
  // depend on the compiler inferring that a non-null `run` implies one.
  const batches = detail?.batches ?? []
  const status = run?.status ?? null
  const busy = loading || pendingAction !== null

  return (
    <section className="score-run-panel" aria-labelledby="score-run-panel-title">
      <div className="metric-row">
        <div>
          <strong id="score-run-panel-title">Score runs</strong>
          <p className="page-copy-block">Run score-all, cancel active work, or replay failed batches.</p>
        </div>
        {status ? (
          <Chip label={statusCopy[status].label} tone={statusCopy[status].tone} />
        ) : null}
      </div>

      {error ? (
        <p className="page-copy-block" role="alert">{error}</p>
      ) : null}

      {run ? (
        <div className="score-run-panel__body">
          <div className="knowledge-base-stats">
            <div className="knowledge-base-stat">
              <span className="metric-row__label">Scored</span>
              <strong>{run.scored_entities} / {run.total_entities}</strong>
            </div>
            <div className="knowledge-base-stat">
              <span className="metric-row__label">Skipped</span>
              <strong>{run.skipped_entities}</strong>
            </div>
            <div className="knowledge-base-stat">
              <span className="metric-row__label">Failed</span>
              <strong>{run.failed_entities}</strong>
            </div>
            <div className="knowledge-base-stat">
              <span className="metric-row__label">Model</span>
              <strong>{run.model_version}</strong>
            </div>
            <div className="knowledge-base-stat">
              <span className="metric-row__label">Catalog</span>
              <strong>{run.catalog_version}</strong>
            </div>
          </div>

          <dl className="score-run-panel__meta" aria-label="Score run metadata">
            <div>
              <dt>Run ID</dt>
              <dd>{run.id}</dd>
            </div>
            <div>
              <dt>Updated</dt>
              <dd title={run.updated_at}>{formatRelativeTime(run.updated_at)}</dd>
            </div>
            {run.replay_of_run_id ? (
              <div>
                <dt>Replay of</dt>
                <dd>{run.replay_of_run_id}</dd>
              </div>
            ) : null}
            {run.error_summary ? (
              <div>
                <dt>Error</dt>
                <dd role="alert">{run.error_summary}</dd>
              </div>
            ) : null}
          </dl>

          {batches.length > 0 ? (
            <ol className="score-run-panel__batches" aria-label="Score run batches">
              {batches.map((batch) => (
                <li key={batch.id}>
                  <span>Batch {batch.batch_number}</span>
                  <Chip label={statusCopy[batch.status].label} tone={statusCopy[batch.status].tone} />
                  <span className="metric-row__label">
                    {batch.entity_ids.length === 1
                      ? '1 entity'
                      : `${batch.entity_ids.length} entities`} | {batch.attempts} attempts
                  </span>
                </li>
              ))}
            </ol>
          ) : null}
        </div>
      ) : (
        <EmptyState
          title={loading ? 'Loading score run' : 'No score run selected'}
          description="Start score-all after ingestion lands entities in this knowledge base."
        />
      )}

      {startReason ? (
        <p className="metric-row__label" role="note">
          {startReason}
        </p>
      ) : null}

      <div className="ingestion-next-actions__buttons">
        <button
          className="page-button page-button--primary"
          disabled={disabled || busy || startDisabled}
          onClick={onStart}
          type="button"
        >
          {pendingAction === 'start' ? 'Starting' : 'Start score-all'}
        </button>
        <button
          className="page-button page-button--secondary"
          disabled={disabled || busy || !canCancel(status)}
          onClick={onCancel}
          type="button"
        >
          {pendingAction === 'cancel' ? 'Canceling' : 'Cancel'}
        </button>
        <button
          className="page-button page-button--secondary"
          disabled={disabled || busy || !canReplay(status)}
          onClick={onReplay}
          type="button"
        >
          {pendingAction === 'replay' ? 'Replaying' : 'Replay failed'}
        </button>
      </div>
    </section>
  )
}
