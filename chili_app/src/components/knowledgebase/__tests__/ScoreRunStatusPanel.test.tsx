import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ScoreRunDetailResponse } from '../../../api/contracts'
import { ScoreRunStatusPanel } from '../ScoreRunStatusPanel'

const detail: ScoreRunDetailResponse = {
  created: false,
  run: {
    catalog_version: 'catalog-2026-08',
    created_at: '2026-08-02T10:00:00Z',
    error_summary: null,
    failed_entities: 1,
    finished_at: null,
    id: 'run-1',
    idempotency_key: 'score-all-kb-1',
    knowledge_base_id: 'kb-1',
    model_version: 'risk-v2',
    replay_of_run_id: null,
    requested_by: 'analyst@example.test',
    scored_entities: 9,
    started_at: '2026-08-02T10:01:00Z',
    status: 'running',
    total_entities: 10,
    updated_at: '2026-08-02T10:02:00Z',
  },
  batches: [
    {
      attempts: 2,
      batch_number: 1,
      created_at: '2026-08-02T10:00:00Z',
      entity_ids: ['provider-1', 'provider-2'],
      error_summary: null,
      finished_at: null,
      id: 'batch-1',
      knowledge_base_id: 'kb-1',
      run_id: 'run-1',
      started_at: '2026-08-02T10:01:00Z',
      status: 'running',
      updated_at: '2026-08-02T10:02:00Z',
    },
  ],
}

describe('ScoreRunStatusPanel', () => {
  it('renders score run progress, version metadata, and batches', () => {
    render(
      <ScoreRunStatusPanel
        detail={detail}
        onCancel={vi.fn()}
        onReplay={vi.fn()}
        onStart={vi.fn()}
      />,
    )

    expect(screen.getAllByText('Running')).toHaveLength(2)
    expect(screen.getByText('9 / 10')).toBeInTheDocument()
    expect(screen.getByText('risk-v2')).toBeInTheDocument()
    expect(screen.getByText('catalog-2026-08')).toBeInTheDocument()
    expect(screen.getByText('Batch 1')).toBeInTheDocument()
    expect(screen.getByText('2 entities | 2 attempts')).toBeInTheDocument()
  })

  it('allows canceling queued or running runs but blocks replay until a terminal failure', () => {
    const onCancel = vi.fn()
    const onReplay = vi.fn()

    render(
      <ScoreRunStatusPanel
        detail={detail}
        onCancel={onCancel}
        onReplay={onReplay}
        onStart={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Replay failed' })).toBeDisabled()
  })

  it('enables replay and shows lineage for a failed replayable run', () => {
    const onReplay = vi.fn()
    render(
      <ScoreRunStatusPanel
        detail={{
          ...detail,
          run: {
            ...detail.run,
            error_summary: 'Batch 1 failed',
            replay_of_run_id: 'run-0',
            status: 'failed',
          },
          batches: [],
        }}
        onCancel={vi.fn()}
        onReplay={onReplay}
        onStart={vi.fn()}
      />,
    )

    const meta = screen.getByLabelText('Score run metadata')
    expect(within(meta).getByText('run-0')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Batch 1 failed')

    fireEvent.click(screen.getByRole('button', { name: 'Replay failed' }))

    expect(onReplay).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('treats replay-created queued runs as active and cancelable', () => {
    const onCancel = vi.fn()
    render(
      <ScoreRunStatusPanel
        detail={{
          ...detail,
          run: {
            ...detail.run,
            replay_of_run_id: 'run-0',
            status: 'queued',
          },
        }}
        onCancel={onCancel}
        onReplay={vi.fn()}
        onStart={vi.fn()}
      />,
    )

    expect(screen.getByText('Queued')).toBeInTheDocument()
    expect(screen.getByText('run-0')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('shows an empty state but still lets a selected knowledge base start score-all', () => {
    const onStart = vi.fn()
    render(
      <ScoreRunStatusPanel
        detail={null}
        onCancel={vi.fn()}
        onReplay={vi.fn()}
        onStart={onStart}
      />,
    )

    expect(screen.getByText('No score run selected')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start score-all' }))

    expect(onStart).toHaveBeenCalledTimes(1)
  })
})
