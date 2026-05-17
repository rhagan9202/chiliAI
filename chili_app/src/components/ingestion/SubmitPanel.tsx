import { Chip } from '../ui/Chip'
import './ingestion.css'

type SubmitPanelProps = {
  canSubmitDocuments: boolean
  canSubmitRecords: boolean
  documentPending: boolean
  recordsPending: boolean
  onSubmitDocuments: () => void
  onSubmitRecords: () => void
}

type SubmitActionProps = {
  buttonLabel: string
  disabled: boolean
  pending: boolean
  pendingLabel: string
  readyLabel: string
  onSubmit: () => void
}

function SubmitAction({
  buttonLabel,
  disabled,
  pending,
  pendingLabel,
  readyLabel,
  onSubmit,
}: SubmitActionProps) {
  return (
    <div className="ingestion-submit-panel__action">
      <button
        aria-busy={pending}
        className="page-button page-button--primary"
        disabled={disabled}
        type="button"
        onClick={onSubmit}
      >
        {buttonLabel}
      </button>
      <span className="ingestion-submit-panel__status" role={pending ? 'status' : undefined}>
        <Chip tone={pending ? 'info' : 'default'} label={pending ? pendingLabel : readyLabel} />
      </span>
    </div>
  )
}

export function SubmitPanel({
  canSubmitDocuments,
  canSubmitRecords,
  documentPending,
  recordsPending,
  onSubmitDocuments,
  onSubmitRecords,
}: SubmitPanelProps) {
  return (
    <section className="ingestion-submit-panel" aria-labelledby="ingestion-submit-title">
      <div className="ingestion-source-panel__header">
        <h3 id="ingestion-submit-title" className="ingestion-source-panel__title">
          Submit ingestion
        </h3>
      </div>

      <div className="ingestion-submit-panel__actions">
        <SubmitAction
          buttonLabel="Submit documents"
          disabled={!canSubmitDocuments || documentPending}
          pending={documentPending}
          pendingLabel="Submitting documents"
          readyLabel="Documents ready"
          onSubmit={onSubmitDocuments}
        />
        <SubmitAction
          buttonLabel="Submit records"
          disabled={!canSubmitRecords || recordsPending}
          pending={recordsPending}
          pendingLabel="Submitting records"
          readyLabel="Records ready"
          onSubmit={onSubmitRecords}
        />
      </div>
    </section>
  )
}
