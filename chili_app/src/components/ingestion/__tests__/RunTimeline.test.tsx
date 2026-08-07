import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render as tlRender, screen, waitFor, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { apiFetch } from '../../../api/client'
import type { WorkflowRunResponse } from '../../../api/contracts'
import type { IngestionReceiptEntry } from '../../../lib/ingestion/types'
import { RunTimeline } from '../RunTimeline'

vi.mock('../../../api/client', () => ({
  apiFetch: vi.fn().mockResolvedValue({ id: 'workflow-1', status: 'cancelled' }),
}))

const apiFetchMock = vi.mocked(apiFetch)

function render(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return tlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const workflows: WorkflowRunResponse[] = [
  {
    id: 'workflow-1',
    workflow_type: 'ingestion',
    status: 'running',
    knowledge_base_id: 'kb-1',
    started_at: '2026-05-17T12:00:00Z',
    updated_at: '2026-05-17T12:01:00Z',
    current_step: 'extract_text',
    last_error: null,
  },
]

const receipts: IngestionReceiptEntry[] = [
  {
    id: 'receipt-1',
    sourceType: 'records',
    status: 'accepted',
    message: 'Accepted 2 claim records.',
    createdAt: '2026-05-17T12:02:00Z',
    receipt: {
      knowledge_base_id: 'kb-1',
      feed_name: 'claims_feed',
      record_type: 'claim_record',
      correlation_id: 'corr-1',
      accepted_count: 2,
      duplicate: false,
      duplicate_count: 0,
      suppressed_existing_count: 0,
      rejected_count: 0,
      created_at: '2026-05-17T12:02:00Z',
    },
  },
]

describe('RunTimeline', () => {
  it('renders an empty state when there are no workflows or receipts', () => {
    render(<RunTimeline workflows={[]} receipts={[]} />)

    expect(screen.getByText('No runs yet')).toBeInTheDocument()
  })

  it('renders workflow type, status, and current step', () => {
    render(<RunTimeline workflows={workflows} receipts={[]} />)

    const list = screen.getByRole('list', { name: /ingestion runs/i })
    const workflowItem = within(list).getByText('ingestion').closest('li')

    expect(workflowItem).not.toBeNull()
    expect(within(workflowItem as HTMLElement).getByText('Running')).toBeInTheDocument()
    expect(within(workflowItem as HTMLElement).getByText('extract_text')).toBeInTheDocument()
  })

  it('renders workflow status labels and descriptions', () => {
    const statusCopy = [
      {
        status: 'queued',
        label: 'Queued',
        description: 'The run is waiting for a worker.',
      },
      {
        status: 'running',
        label: 'Running',
        description: 'This run is being processed now.',
      },
      {
        status: 'completed',
        label: 'Completed',
        description: 'Investigation data is ready to review.',
      },
      {
        status: 'failed',
        label: 'Failed',
        description: 'Review the error and retry when fixed.',
      },
      {
        status: 'cancelled',
        label: 'Cancelled',
        description: 'The run was stopped before completion.',
      },
    ] as const

    render(
      <RunTimeline
        workflows={statusCopy.map(({ status }, index) => ({
          ...workflows[0],
          id: `workflow-${status}`,
          status,
          updated_at: `2026-05-17T12:0${index}:00Z`,
          current_step: `step-${status}`,
        }))}
        receipts={[]}
      />,
    )

    for (const { label, description } of statusCopy) {
      expect(screen.getByText(label)).toBeInTheDocument()
      expect(screen.getByText(description)).toBeInTheDocument()
    }
  })

  it('renders receipt source type, status, and message', () => {
    render(<RunTimeline workflows={[]} receipts={receipts} />)

    const list = screen.getByRole('list', { name: /ingestion runs/i })
    const receiptItem = within(list).getByText('records').closest('li')

    expect(receiptItem).not.toBeNull()
    expect(within(receiptItem as HTMLElement).getByText('Accepted')).toBeInTheDocument()
    expect(within(receiptItem as HTMLElement).getByText('Accepted 2 claim records.')).toBeInTheDocument()
  })

  it('renders receipt status labels and descriptions', () => {
    const statusCopy = [
      {
        status: 'accepted',
        label: 'Accepted',
        description: 'Submission accepted. Watch for queued or running workflow updates.',
      },
      {
        status: 'failed',
        label: 'Failed',
        description: 'Submission failed before a run could start.',
      },
    ] as const

    render(
      <RunTimeline
        workflows={[]}
        receipts={statusCopy.map(({ status }, index) => ({
          ...receipts[0],
          id: `receipt-${status}`,
          status,
          createdAt: `2026-05-17T12:0${index}:00Z`,
          message: `${status} receipt message`,
        }))}
      />,
    )

    for (const { label, description } of statusCopy) {
      expect(screen.getByText(label)).toBeInTheDocument()
      expect(screen.getByText(description)).toBeInTheDocument()
    }
  })

  it('sorts workflows and receipts by timestamp with newest first', () => {
    render(<RunTimeline workflows={workflows} receipts={receipts} />)

    const list = screen.getByRole('list', { name: /ingestion runs/i })
    const items = within(list).getAllByRole('listitem')

    expect(within(items[0]).getByText('records')).toBeInTheDocument()
    expect(within(items[1]).getByText('ingestion')).toBeInTheDocument()
  })

  it('summarises accepted, duplicate, and rejected counts for a receipt', () => {
    render(
      <RunTimeline
        workflows={[]}
        receipts={[
          {
            ...receipts[0],
            receipt: {
              ...receipts[0].receipt!,
              accepted_count: 8,
              duplicate_count: 1,
              rejected_count: 2,
              rejected: [
                { index: 3, reason: 'missing DESYNPUF_ID' },
                { index: 5, reason: 'invalid CLM_FROM_DT' },
              ],
            },
          },
        ]}
      />,
    )

    expect(screen.getByText('8 accepted, 1 duplicate, 2 rejected')).toBeInTheDocument()
    const rejectedList = screen.getByRole('list', { name: /rejected rows/i })
    expect(rejectedList).toHaveTextContent('Row 3')
    expect(rejectedList).toHaveTextContent('missing DESYNPUF_ID')
    expect(rejectedList).toHaveTextContent('Row 5')
    expect(rejectedList).toHaveTextContent('invalid CLM_FROM_DT')
  })

  it('shows a duplicate submission no-op indicator when the receipt is a duplicate', () => {
    render(
      <RunTimeline
        workflows={[]}
        receipts={[
          {
            ...receipts[0],
            receipt: {
              ...receipts[0].receipt!,
              accepted_count: 0,
              duplicate: true,
              duplicate_count: 2,
            },
          },
        ]}
      />,
    )

    expect(screen.getByText(/duplicate submission \(no-op\)/i)).toBeInTheDocument()
  })

  it('bounds the rejected-row list and notes the remainder when there are many rejections', () => {
    const rejected = Array.from({ length: 9 }, (_, index) => ({
      index,
      reason: `reason ${index}`,
    }))

    render(
      <RunTimeline
        workflows={[]}
        receipts={[
          {
            ...receipts[0],
            receipt: {
              ...receipts[0].receipt!,
              accepted_count: 0,
              rejected_count: 9,
              rejected,
            },
          },
        ]}
      />,
    )

    const rejectedList = screen.getByRole('list', { name: /rejected rows/i })
    expect(within(rejectedList).getAllByRole('listitem')).toHaveLength(5)
    expect(screen.getByText(/4 more/)).toBeInTheDocument()
  })

  it('renders failure detail for failed workflows', () => {
    render(<RunTimeline workflows={[{
      ...workflows[0],
      status: 'failed',
      current_step: 'failed',
      last_error: 'Parser failed after retries.',
    }]} receipts={[]} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Parser failed after retries.')
  })

  it('shows a cancel control only for non-terminal workflows', () => {
    render(<RunTimeline workflows={workflows} receipts={[]} />)
    expect(screen.getByRole('button', { name: /cancel ingestion workflow/i })).toBeInTheDocument()
  })

  it('hides the cancel control for terminal workflows', () => {
    render(
      <RunTimeline
        workflows={[{ ...workflows[0], status: 'completed', current_step: 'ready' }]}
        receipts={[]}
      />,
    )
    expect(screen.queryByRole('button', { name: /cancel/i })).not.toBeInTheDocument()
  })

  it('cancels the workflow via the API when the cancel control is clicked', async () => {
    apiFetchMock.mockClear()
    render(<RunTimeline workflows={workflows} receipts={[]} />)

    fireEvent.click(screen.getByRole('button', { name: /cancel ingestion workflow/i }))

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith('/workflows/workflow-1/cancel', {
        method: 'POST',
      })
    })
  })
})

describe('RunTimeline awaiting approval', () => {
  it('labels a parked run rather than leaving it blank', () => {
    const parked: WorkflowRunResponse[] = [
      {
        id: 'workflow-parked',
        workflow_type: 'ingestion',
        status: 'awaiting_approval',
        knowledge_base_id: 'kb-1',
        started_at: '2026-05-17T12:00:00Z',
        updated_at: '2026-05-17T12:01:00Z',
        current_step: 'gate',
        last_error: null,
      },
    ]

    render(<RunTimeline workflows={parked} receipts={[]} />)

    expect(screen.getByText('Awaiting approval')).toBeInTheDocument()
    expect(screen.getByText('gate')).toBeInTheDocument()
  })

  it('lets a reviewer cancel a run parked at a gate', () => {
    // The backend permits it — a parked run is non-terminal — so hiding the
    // control would leave a reviewer who decides *not* to approve with no way
    // to close the run out.
    const parked: WorkflowRunResponse[] = [
      {
        id: 'workflow-parked',
        workflow_type: 'ingestion',
        status: 'awaiting_approval',
        knowledge_base_id: 'kb-1',
        started_at: '2026-05-17T12:00:00Z',
        updated_at: '2026-05-17T12:01:00Z',
        current_step: 'gate',
        last_error: null,
      },
    ]

    render(<RunTimeline workflows={parked} receipts={[]} />)

    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })
})

describe('RunTimeline approval decisions', () => {
  const parked: WorkflowRunResponse[] = [
    {
      id: 'workflow-parked',
      workflow_type: 'ingestion',
      status: 'awaiting_approval',
      knowledge_base_id: 'kb-1',
      started_at: '2026-05-17T12:00:00Z',
      updated_at: '2026-05-17T12:01:00Z',
      current_step: 'gate',
      last_error: null,
    },
  ]

  it('offers approve and reject on a run parked at a gate', () => {
    render(<RunTimeline workflows={parked} receipts={[]} />)

    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument()
  })

  it('does not offer approval on a run that is merely running', () => {
    render(<RunTimeline workflows={workflows} receipts={[]} />)

    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
  })

  it('approves the step the run is parked on', async () => {
    apiFetchMock.mockResolvedValueOnce({ id: 'workflow-parked', status: 'queued' })
    render(<RunTimeline workflows={parked} receipts={[]} />)

    fireEvent.click(screen.getByRole('button', { name: /approve/i }))

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith(
        '/workflows/workflow-parked/steps/gate/approve',
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('requires a reason before rejecting', async () => {
    render(<RunTimeline workflows={parked} receipts={[]} />)

    fireEvent.click(screen.getByRole('button', { name: /reject/i }))

    // "Rejected" with no reason is an audit record that explains nothing, so
    // the API requires one and the UI must not let it be submitted empty.
    expect(screen.getByRole('button', { name: /confirm rejection/i })).toBeDisabled()
  })

  it('sends the reason when rejecting', async () => {
    apiFetchMock.mockResolvedValueOnce({ id: 'workflow-parked', status: 'failed' })
    render(<RunTimeline workflows={parked} receipts={[]} />)

    fireEvent.click(screen.getByRole('button', { name: /reject/i }))
    fireEvent.change(screen.getByLabelText(/rejection reason/i), {
      target: { value: 'insufficient evidence' },
    })
    fireEvent.click(screen.getByRole('button', { name: /confirm rejection/i }))

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith(
        '/workflows/workflow-parked/steps/gate/reject',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ reason: 'insufficient evidence' }),
        }),
      )
    })
  })
})
