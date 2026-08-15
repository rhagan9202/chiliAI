import { useState } from 'react'

import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import { StatusChip } from '../status/StatusChip'
import { formatRelativeTime } from '../status/formatters'
import {
  useApproveWorkflowStep,
  useCancelWorkflow,
  useRejectWorkflowStep,
} from '../../api/workflows'
import type { RecordIngestReceipt, WorkflowRunResponse } from '../../api/contracts'
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
  awaiting_approval: {
    label: 'Awaiting approval',
    description: 'Paused at an approval step. It resumes once a reviewer approves.',
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

function isCancellable(status: WorkflowRunResponse['status']): boolean {
  // `awaiting_approval` is included because the backend permits it — the run is
  // non-terminal, so cancel_workflow honours it. Omitting it would leave a run
  // parked at a gate with no exit but approval, and a reviewer who decides
  // *not* to approve would have no way to close it out.
  return status === 'running' || status === 'queued' || status === 'awaiting_approval'
}

function receiptCountsSummary(receipt: RecordIngestReceipt): string {
  const parts = [
    `${receipt.accepted_count} accepted`,
    `${receipt.duplicate_count} duplicate`,
    `${receipt.rejected_count} rejected`,
  ]
  // Records are insert-only: rows whose id already exists are skipped rather
  // than updated. The API has always reported how many; the UI used to drop
  // the number, so a submission could report zero rejections and still change
  // nothing.
  if (receipt.suppressed_existing_count > 0) {
    parts.push(`${receipt.suppressed_existing_count} already existed (skipped)`)
  }
  return parts.join(', ')
}

type RunTimelineProps = {
  workflows: WorkflowRunResponse[]
}

function timestampValue(timestamp: string) {
  const value = Date.parse(timestamp)
  return Number.isNaN(value) ? 0 : value
}

function sortedWorkflows(workflows: WorkflowRunResponse[]): WorkflowRunResponse[] {
  return [...workflows].sort(
    (first, second) => timestampValue(second.updated_at) - timestampValue(first.updated_at),
  )
}

function isAwaitingApproval(status: WorkflowRunResponse['status']): boolean {
  return status === 'awaiting_approval'
}

export function RunTimeline({ workflows }: RunTimelineProps) {
  const cancelWorkflow = useCancelWorkflow()
  const approveStep = useApproveWorkflowStep()
  const rejectStep = useRejectWorkflowStep()
  // Which run has its rejection form open, and what reason has been typed.
  // Rejection is two-step on purpose: the API requires a reason, so a
  // single-click reject would only ever produce a validation error.
  const [rejecting, setRejecting] = useState<string | null>(null)
  const [reason, setReason] = useState('')

  if (workflows.length === 0) {
    return (
      <EmptyState
        title="No runs yet"
        description="Submit documents or records to start tracking ingestion activity."
      />
    )
  }

  return (
    <section className="ingestion-run-timeline" aria-labelledby="ingestion-runs-title">
      <div className="ingestion-source-panel__header">
        <h3 id="ingestion-runs-title" className="ingestion-source-panel__title">
          Run timeline
        </h3>
      </div>

      <ol className="ingestion-run-timeline__list" aria-label="Ingestion runs">
        {sortedWorkflows(workflows).map((workflow) => {
          const statusCopy = workflowStatusCopy[workflow.status]

          return (
              <li className="ingestion-run-timeline__item" key={workflow.id}>
                <div className="ingestion-run-timeline__marker" aria-hidden="true" />
                <div className="ingestion-run-timeline__body">
                  <div className="ingestion-run-timeline__header">
                    <span className="ingestion-run-timeline__title">{workflow.workflow_type}</span>
                    <StatusChip kind="workflow" status={workflow.status} />
                    {isAwaitingApproval(workflow.status) ? (
                      <>
                        <button
                          type="button"
                          className="page-button page-button--primary"
                          aria-label={`Approve ${workflow.current_step} step`}
                          disabled={approveStep.isPending}
                          onClick={() => approveStep.mutate({
                            workflowId: workflow.id,
                            stepId: workflow.current_step,
                          })}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          className="page-button page-button--secondary"
                          aria-label={`Reject ${workflow.current_step} step`}
                          onClick={() => {
                            setRejecting(workflow.id)
                            setReason('')
                          }}
                        >
                          Reject
                        </button>
                      </>
                    ) : null}
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
                  {rejecting === workflow.id ? (
                    <div className="ingestion-run-timeline__reject">
                      <label htmlFor={`reject-reason-${workflow.id}`}>Rejection reason</label>
                      <input
                        id={`reject-reason-${workflow.id}`}
                        type="text"
                        value={reason}
                        onChange={(event) => setReason(event.target.value)}
                      />
                      <button
                        type="button"
                        className="page-button page-button--primary"
                        disabled={reason.trim().length === 0 || rejectStep.isPending}
                        onClick={() => {
                          rejectStep.mutate({
                            workflowId: workflow.id,
                            stepId: workflow.current_step,
                            reason: reason.trim(),
                          })
                          setRejecting(null)
                        }}
                      >
                        Confirm rejection
                      </button>
                    </div>
                  ) : null}
                  <dl className="ingestion-run-timeline__meta" aria-label={`${workflow.id} workflow details`}>
                    <div>
                      <dt>Current step</dt>
                      <dd>{workflow.current_step}</dd>
                    </div>
                    <div>
                      <dt>Updated</dt>
                      {/* Timelines read in relative time; the exact instant stays
                          recoverable on hover rather than shouting a raw ISO string. */}
                      <dd title={workflow.updated_at}>{formatRelativeTime(workflow.updated_at)}</dd>
                    </div>
                  </dl>
                  {workflow.status === 'failed' ? (
                    <p className="ingestion-run-timeline__message" role="alert">
                      {workflow.last_error ?? 'This step failed and no reason was reported. Retry the run, or ask an administrator to check the service logs.'}
                    </p>
                  ) : null}
                  {/* Records runs carry their ingest receipt; document runs
                      have none. Both come from the server, so the counts
                      survive a reload and are visible to every reader. */}
                  {workflow.receipt ? (
                    <ReceiptDetails receipt={workflow.receipt} entryId={workflow.id} />
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
