import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import type { WorkflowRunResponse } from '../../api/contracts'
import type { IngestionReceiptEntry } from '../../lib/ingestion/types'
import './ingestion.css'

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

            return (
              <li className="ingestion-run-timeline__item" key={item.id}>
                <div className="ingestion-run-timeline__marker" aria-hidden="true" />
                <div className="ingestion-run-timeline__body">
                  <div className="ingestion-run-timeline__header">
                    <span className="ingestion-run-timeline__title">{workflow.workflow_type}</span>
                    <Chip tone={workflowTone(workflow.status)} label={workflow.status} />
                  </div>
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
                </div>
              </li>
            )
          }

          const { receipt } = item

          return (
            <li className="ingestion-run-timeline__item" key={item.id}>
              <div className="ingestion-run-timeline__marker" aria-hidden="true" />
              <div className="ingestion-run-timeline__body">
                <div className="ingestion-run-timeline__header">
                  <span className="ingestion-run-timeline__title">{receipt.sourceType}</span>
                  <Chip tone={receiptTone(receipt.status)} label={receipt.status} />
                </div>
                <p className="ingestion-run-timeline__message">{receipt.message}</p>
                {receipt.receipt ? (
                  <dl className="ingestion-run-timeline__meta" aria-label={`${receipt.id} receipt details`}>
                    <div>
                      <dt>Feed</dt>
                      <dd>{receipt.receipt.feed_name}</dd>
                    </div>
                    <div>
                      <dt>Correlation</dt>
                      <dd>{receipt.receipt.correlation_id}</dd>
                    </div>
                  </dl>
                ) : null}
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
