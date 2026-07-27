import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import { useCancelWorkflow } from '../../api/workflows'
import type { RecordIngestReceipt, WorkflowRunResponse } from '../../api/contracts'
import type { IngestionReceiptEntry } from '../../lib/ingestion/types'
import './ingestion.css'

const MAX_REJECTED_ROWS_SHOWN = 5

const workflowStatusCopy: Record<
  WorkflowRunResponse['status'],
  { label: string; description: string }
> = {
  queued: {
    label: 'Queued',
    description: 'The run is waiting for a worker.',
  },
  running: {
    label: 'Running',
    description: 'This run is being processed now.',
  },
  completed: {
    label: 'Completed',
    description: 'Investigation data is ready to review.',
  },
  failed: {
    label: 'Failed',
    description: 'Review the error and retry when fixed.',
  },
  cancelled: {
    label: 'Cancelled',
    description: 'The run was stopped before completion.',
  },
}

const receiptStatusCopy: Record<
  IngestionReceiptEntry['status'],
  { label: string; description: string }
> = {
  accepted: {
    label: 'Accepted',
    description: 'Submission accepted. Watch for queued or running workflow updates.',
  },
  failed: {
    label: 'Failed',
    description: 'Submission failed before a run could start.',
  },
}

function isCancellable(status: WorkflowRunResponse['status']): boolean {
  return status === 'running' || status === 'queued'
}

function receiptCountsSummary(receipt: RecordIngestReceipt): string {
  return [
    `${receipt.accepted_count} accepted`,
    `${receipt.duplicate_count} duplicate`,
    `${receipt.rejected_count} rejected`,
  ].join(', ')
}

type RunTimelineProps = {
  receipts: IngestionReceiptEntry[]
  workflows: WorkflowRunResponse[]
}

type TimelineItem =
  | {
      id: string
      timestamp: string
      type: 'workflow'
      workflow: WorkflowRunResponse
    }
  | {
      id: string
      timestamp: string
      type: 'receipt'
      receipt: IngestionReceiptEntry
    }

function workflowTone(status: WorkflowRunResponse['status']) {
  if (status === 'completed') {
    return 'success'
  }

  if (status === 'failed' || status === 'cancelled') {
    return 'danger'
  }

  return 'info'
}

function receiptTone(status: IngestionReceiptEntry['status']) {
  return status === 'accepted' ? 'success' : 'danger'
}

function timestampValue(timestamp: string) {
  const value = Date.parse(timestamp)
  return Number.isNaN(value) ? 0 : value
}

function buildTimelineItems(
  workflows: WorkflowRunResponse[],
  receipts: IngestionReceiptEntry[],
): TimelineItem[] {
  return [
    ...workflows.map((workflow) => ({
      id: `workflow-${workflow.id}`,
      timestamp: workflow.updated_at,
      type: 'workflow' as const,
      workflow,
    })),
    ...receipts.map((receipt) => ({
      id: `receipt-${receipt.id}`,
      timestamp: receipt.createdAt,
      type: 'receipt' as const,
      receipt,
    })),
  ].sort((first, second) => (
    timestampValue(second.timestamp) - timestampValue(first.timestamp)
  ))
}

export function RunTimeline({ receipts, workflows }: RunTimelineProps) {
  const cancelWorkflow = useCancelWorkflow()

  if (receipts.length === 0 && workflows.length === 0) {
    return (
      <EmptyState
        title="No runs yet"
        description="Submit documents or records to start tracking ingestion activity."
      />
    )
  }

  const timelineItems = buildTimelineItems(workflows, receipts)

  return (
    <section className="ingestion-run-timeline" aria-labelledby="ingestion-runs-title">
      <div className="ingestion-source-panel__header">
        <h3 id="ingestion-runs-title" className="ingestion-source-panel__title">
          Run timeline
        </h3>
      </div>

      <ol className="ingestion-run-timeline__list" aria-label="Ingestion runs">
        {timelineItems.map((item) => {
          if (item.type === 'workflow') {
            const { workflow } = item
            const statusCopy = workflowStatusCopy[workflow.status]

            return (
              <li className="ingestion-run-timeline__item" key={item.id}>
                <div className="ingestion-run-timeline__marker" aria-hidden="true" />
                <div className="ingestion-run-timeline__body">
                  <div className="ingestion-run-timeline__header">
                    <span className="ingestion-run-timeline__title">{workflow.workflow_type}</span>
                    <Chip tone={workflowTone(workflow.status)} label={statusCopy.label} />
                    {isCancellable(workflow.status) ? (
                      <button
                        type="button"
                        className="page-button page-button--secondary"
                        aria-label={`Cancel ${workflow.workflow_type} workflow`}
                        disabled={cancelWorkflow.isPending}
                        onClick={() => cancelWorkflow.mutate(workflow.id)}
                      >
                        Cancel
                      </button>
                    ) : null}
                  </div>
                  <p className="ingestion-run-timeline__message">{statusCopy.description}</p>
                  <dl className="ingestion-run-timeline__meta" aria-label={`${workflow.id} workflow details`}>
                    <div>
                      <dt>Current step</dt>
                      <dd>{workflow.current_step}</dd>
                    </div>
                    <div>
                      <dt>Updated</dt>
                      <dd>{workflow.updated_at}</dd>
                    </div>
                  </dl>
                  {workflow.status === 'failed' ? (
                    <p className="ingestion-run-timeline__message" role="alert">
                      {workflow.last_error ?? 'This step failed and no reason was reported. Retry the run, or ask an administrator to check the service logs.'}
                    </p>
                  ) : null}
                </div>
              </li>
            )
          }

          const { receipt } = item
          const statusCopy = receiptStatusCopy[receipt.status]

          return (
            <li className="ingestion-run-timeline__item" key={item.id}>
              <div className="ingestion-run-timeline__marker" aria-hidden="true" />
              <div className="ingestion-run-timeline__body">
                <div className="ingestion-run-timeline__header">
                  <span className="ingestion-run-timeline__title">{receipt.sourceType}</span>
                  <Chip tone={receiptTone(receipt.status)} label={statusCopy.label} />
                </div>
                <p className="ingestion-run-timeline__message">{statusCopy.description}</p>
                <p className="ingestion-run-timeline__message">{receipt.message}</p>
                {receipt.receipt ? (
                  <ReceiptDetails receipt={receipt.receipt} entryId={receipt.id} />
                ) : null}
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

function ReceiptDetails({
  receipt,
  entryId,
}: {
  receipt: RecordIngestReceipt
  entryId: string
}) {
  const rejected = receipt.rejected ?? []
  const shownRejected = rejected.slice(0, MAX_REJECTED_ROWS_SHOWN)
  const remainingRejected = rejected.length - shownRejected.length

  return (
    <div className="ingestion-run-timeline__receipt">
      <div className="ingestion-run-timeline__counts">
        <span className="ingestion-run-timeline__counts-summary">
          {receiptCountsSummary(receipt)}
        </span>
        {receipt.duplicate ? (
          <Chip tone="warning" label="Duplicate submission (no-op)" />
        ) : null}
      </div>

      <dl className="ingestion-run-timeline__meta" aria-label={`${entryId} receipt details`}>
        <div>
          <dt>Feed</dt>
          <dd>{receipt.feed_name}</dd>
        </div>
        <div>
          <dt>Correlation</dt>
          <dd>{receipt.correlation_id}</dd>
        </div>
      </dl>

      {shownRejected.length > 0 ? (
        <div className="ingestion-run-timeline__rejected">
          <p className="ingestion-run-timeline__rejected-title">Rejected rows</p>
          <ul
            className="ingestion-run-timeline__rejected-list"
            aria-label={`${entryId} rejected rows`}
          >
            {shownRejected.map((row) => (
              <li key={`${entryId}-rejected-${row.index}`}>
                <span className="ingestion-run-timeline__rejected-index">Row {row.index}</span>
                <span className="ingestion-run-timeline__rejected-reason">{row.reason}</span>
              </li>
            ))}
          </ul>
          {remainingRejected > 0 ? (
            <p className="ingestion-run-timeline__rejected-more">
              and {remainingRejected} more rejected row{remainingRejected === 1 ? '' : 's'}.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
