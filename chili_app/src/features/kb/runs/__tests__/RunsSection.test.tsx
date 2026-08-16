import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RunsSection } from '../RunsSection'

function renderSection(entityCount: number) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    )
  }

  return render(<RunsSection knowledgeBaseId="kb-1" entityCount={entityCount} />, {
    wrapper: Wrapper,
  })
}

const workflow = {
  id: 'wf-1',
  workflow_type: 'ingestion',
  status: 'completed',
  knowledge_base_id: 'kb-1',
  created_at: '2026-08-15T12:00:00Z',
  updated_at: '2026-08-15T12:01:00Z',
  steps: [],
  metadata: {},
  receipt: null,
}

type MockScoreRun = {
  catalog_version: string
  created_at: string
  error_summary: string | null
  failed_entities: number
  finished_at: string | null
  id: string
  idempotency_key: string | null
  knowledge_base_id: string
  model_version: string
  replay_of_run_id: string | null
  requested_by: string | null
  scored_entities: number
  started_at: string | null
  status: string
  total_entities: number
  updated_at: string
}

const latestScoreRun: MockScoreRun = {
  catalog_version: 'cms-fraud-features-v1',
  created_at: '2026-08-02T09:00:00Z',
  error_summary: null,
  failed_entities: 0,
  finished_at: null,
  id: 'score-run-latest',
  idempotency_key: null,
  knowledge_base_id: 'kb-1',
  model_version: 'risk-linear-v1',
  replay_of_run_id: null,
  requested_by: 'operator-1',
  scored_entities: 2,
  started_at: '2026-08-02T09:00:00Z',
  status: 'running',
  total_entities: 4,
  updated_at: '2026-08-02T09:01:00Z',
}

const originalFetch = globalThis.fetch

let workflowItems: unknown[] = [workflow]
let scoreRunItems: MockScoreRun[] = []

beforeEach(() => {
  workflowItems = [workflow]
  scoreRunItems = []
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.includes('/workflows')) {
      return new Response(JSON.stringify({ items: workflowItems, total: workflowItems.length }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }
    if (url.includes('/score-runs') && init?.method === 'POST') {
      const body =
        typeof init.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : {}
      const run: MockScoreRun = {
        ...latestScoreRun,
        catalog_version: String(body.catalog_version ?? 'cms-fraud-features-v1'),
        id: 'score-run-started',
        model_version: String(body.model_version ?? 'risk-linear-v1'),
        scored_entities: 0,
        started_at: null,
        status: 'queued',
        total_entities: 2,
      }
      return new Response(JSON.stringify({ run, batches: [], created: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }
    const detailMatch = url.match(/\/score-runs\/([^/?]+)$/)
    if (detailMatch) {
      const run =
        scoreRunItems.find((item) => item.id === detailMatch[1]) ??
        (detailMatch[1] === 'score-run-started'
          ? { ...latestScoreRun, id: 'score-run-started', status: 'queued' }
          : null)
      if (run) {
        return new Response(JSON.stringify({ run, batches: [], created: false }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      }
    }
    if (url.includes('/score-runs')) {
      return new Response(
        JSON.stringify({ items: scoreRunItems, total: scoreRunItems.length, limit: 1, offset: 0 }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    }
    throw new Error(`unexpected request: ${url}`)
  }) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

describe('RunsSection', () => {
  it('renders the runs the server reports', async () => {
    renderSection(12)

    await waitFor(() => {
      expect(screen.getByText('ingestion')).toBeInTheDocument()
    })
  })

  it('disables the score run start and names the blocker when there are no entities', async () => {
    renderSection(0)

    const start = await screen.findByRole('button', { name: 'Start score-all' })
    expect(start).toBeDisabled()
    expect(
      screen.getByText('Start requires ingested entities in this knowledge base.'),
    ).toBeInTheDocument()
  })

  it('enables the score run start once the knowledge base has entities', async () => {
    renderSection(12)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Start score-all' })).toBeEnabled()
    })
    expect(
      screen.queryByText('Start requires ingested entities in this knowledge base.'),
    ).not.toBeInTheDocument()
  })

  // Moved from KnowledgeBaseManagerPage.test.tsx: the page used to hide the
  // run timeline card entirely when a knowledge base had no workflows
  // (UXA-305, deduplicating stacked "nothing here yet" cards). Now that the
  // timeline lives in its own section, it always renders — with an empty
  // state when there is nothing to show — matching the section's role as a
  // standalone route rather than one of several stacked aside cards.
  it('shows an empty state instead of the timeline when there are no workflows', async () => {
    workflowItems = []
    renderSection(12)

    expect(
      await screen.findByText('Submitting documents or records starts a run, and it appears here.'),
    ).toBeInTheDocument()
    expect(screen.getByText('No runs yet')).toBeInTheDocument()
  })

  // Rehomed from KnowledgeBaseManagerPage.test.tsx: scoring everything is the
  // server's business, so the client names no entity ids and mints no
  // idempotency key of its own.
  it('starts score-all without requiring client-side entity ids', async () => {
    renderSection(12)

    await userEvent.click(await screen.findByRole('button', { name: 'Start score-all' }))

    await screen.findByText('score-run-started')
    const startCall = vi.mocked(globalThis.fetch).mock.calls.find((call) => {
      const url = String(call[0])
      return url.endsWith('/knowledgebases/kb-1/score-runs') && call[1]?.method === 'POST'
    })
    expect(startCall).toBeDefined()
    const body = JSON.parse(String(startCall?.[1]?.body)) as Record<string, unknown>
    expect(body).toMatchObject({
      batch_size: 100,
      catalog_version: 'cms-fraud-features-v1',
      model_version: 'risk-linear-v1',
    })
    expect(body).not.toHaveProperty('entity_ids')
    expect(body).not.toHaveProperty('idempotency_key')
  })

  // Rehomed: the panel reads the durable run rather than only runs started in
  // this session, so a reload does not lose sight of one already in flight.
  it('hydrates the score-run panel from the latest durable run', async () => {
    scoreRunItems = [latestScoreRun]
    renderSection(12)

    expect(await screen.findByText('score-run-latest')).toBeInTheDocument()
    expect(screen.getByText('2 / 4')).toBeInTheDocument()
  })
})
