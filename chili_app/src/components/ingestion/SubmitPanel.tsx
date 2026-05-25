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
  canSubmit: boolean
  disabled: boolean
  pending: boolean
  pendingLabel: string
  readyLabel: string
  unavailableLabel: string
  onSubmit: () => void
}

function getStatusLabel({
  canSubmit,
  pending,
  pendingLabel,
  readyLabel,
  unavailableLabel,
}: Pick<
  SubmitActionProps,
  'canSubmit' | 'pending' | 'pendingLabel' | 'readyLabel' | 'unavailableLabel'
>) {
  if (pending) {
    return pendingLabel
  }

  return canSubmit ? readyLabel : unavailableLabel
}

function SubmitAction({
  buttonLabel,
  canSubmit,
  disabled,
  pending,
  pendingLabel,
  readyLabel,
  unavailableLabel,
  onSubmit,
}: SubmitActionProps) {
  const statusLabel = getStatusLabel({
    canSubmit,
    pending,
    pendingLabel,
    readyLabel,
    unavailableLabel,
  })
  const statusTone = pending ? 'info' : canSubmit ? 'default' : 'warning'

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
        <Chip tone={statusTone} label={statusLabel} />
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
          canSubmit={canSubmitDocuments}
          disabled={!canSubmitDocuments || documentPending}
          pending={documentPending}
          pendingLabel="Submitting documents"
          readyLabel="Documents ready"
          unavailableLabel="Select documents"
          onSubmit={onSubmitDocuments}
        />
        <SubmitAction
          buttonLabel="Submit records"
          canSubmit={canSubmitRecords}
          disabled={!canSubmitRecords || recordsPending}
          pending={recordsPending}
          pendingLabel="Submitting records"
          readyLabel="Records ready"
          unavailableLabel="Parse records"
          onSubmit={onSubmitRecords}
        />
      </div>
    </section>
  )
}
