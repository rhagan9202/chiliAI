import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { WorkflowRunResponse } from '../../../api/contracts'
import type { IngestionReceiptEntry } from '../../../lib/ingestion/types'
import { RunTimeline } from '../RunTimeline'

const workflows: WorkflowRunResponse[] = [
  {
    id: 'workflow-1',
    workflow_type: 'ingestion',
    status: 'running',
    knowledge_base_id: 'kb-1',
    started_at: '2026-05-17T12:00:00Z',
    updated_at: '2026-05-17T12:01:00Z',
    current_step: 'extract_text',
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
    expect(within(workflowItem as HTMLElement).getByText('running')).toBeInTheDocument()
    expect(within(workflowItem as HTMLElement).getByText('extract_text')).toBeInTheDocument()
  })

  it('renders receipt source type, status, and message', () => {
    render(<RunTimeline workflows={[]} receipts={receipts} />)

    const list = screen.getByRole('list', { name: /ingestion runs/i })
    const receiptItem = within(list).getByText('records').closest('li')

    expect(receiptItem).not.toBeNull()
    expect(within(receiptItem as HTMLElement).getByText('accepted')).toBeInTheDocument()
    expect(within(receiptItem as HTMLElement).getByText('Accepted 2 claim records.')).toBeInTheDocument()
  })

  it('sorts workflows and receipts by timestamp with newest first', () => {
    render(<RunTimeline workflows={workflows} receipts={receipts} />)

    const list = screen.getByRole('list', { name: /ingestion runs/i })
    const items = within(list).getAllByRole('listitem')

    expect(within(items[0]).getByText('records')).toBeInTheDocument()
    expect(within(items[1]).getByText('ingestion')).toBeInTheDocument()
  })
})
