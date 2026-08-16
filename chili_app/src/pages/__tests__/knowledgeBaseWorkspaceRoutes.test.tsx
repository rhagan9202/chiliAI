/**
 * The knowledge-bases route table, mounted for real.
 *
 * The two page suites next to this one stub the section children, which is
 * right for testing the pages' own logic — but it leaves the seam this split
 * introduced untested: the `*Route` wrappers, and the outlet context they read
 * the loaded knowledge base from. Nothing else in the suite renders a section
 * through that context, so dropping `context={…}` on the workspace's `Outlet`
 * would crash every section at runtime with vitest still green.
 *
 * This mounts `knowledgeBaseRoutes` itself — the same array `router.tsx`
 * spreads into the authenticated shell — so the wrappers, the context, and the
 * legacy redirect are all exercised as shipped.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { knowledgeBaseRoutes } from '../../app/router'
import { useIngestionDraftStore } from '../../stores/ingestionDraftStore'

const medicareKb = {
  id: 'kb-1',
  name: 'Fraud KB',
  description: 'Active corpus',
  status: 'ready',
  document_count: 0,
  entity_count: 0,
  relationship_count: 0,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-14T00:00:00Z',
  domain: 'medicare_fraud',
}

const domainConfig = {
  domain: { name: 'medicare_fraud', display_name: 'Medicare Fraud', description: '' },
  entities: [],
  relationships: [],
  capabilities: {
    timeseries: true,
    gnn: true,
    risk_scoring: true,
    rag_chat: true,
    explainability: true,
    structured_ingestion: true,
  },
  ingestion: {},
  validation: {
    max_file_size_mb: 50,
    allowed_content_types: ['text/plain'],
    max_query_length: 10000,
    max_rag_question_length: 5000,
  },
  records: { feeds: [] },
  alerts: { thresholds: {} },
}

const originalFetch = globalThis.fetch

/** URLs of every DELETE issued, so the delete path can be observed. */
function deleteRequests(): string[] {
  const mock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
  return mock.mock.calls
    .filter((call) => (call[1] as RequestInit | undefined)?.method === 'DELETE')
    .map((call) => String(call[0]))
}

beforeEach(() => {
  useIngestionDraftStore.getState().reset()
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const json = (payload: unknown) =>
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })

    if (init?.method === 'DELETE') return new Response(null, { status: 204 })
    if (url.endsWith('/config/domain')) return json(domainConfig)
    if (url.endsWith('/knowledgebases')) return json({ items: [medicareKb], total: 1 })
    if (url.endsWith('/knowledgebases/kb-1')) return json(medicareKb)
    if (url.includes('/documents')) return json({ items: [], total: 0 })
    if (url.includes('/workflows')) return json({ items: [], total: 0 })
    if (url.includes('/score-runs')) return json({ items: [], total: 0 })
    throw new Error(`unexpected request: ${url}`)
  }) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

function renderAt(initialEntry: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  // The exported entries carry relative paths, exactly as the shell nests
  // them; wrapping in a pathless "/" parent resolves them the same way.
  const testRouter = createMemoryRouter([{ path: '/', children: knowledgeBaseRoutes }], {
    initialEntries: [initialEntry],
  })

  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={testRouter} />
    </QueryClientProvider>,
  )
  return testRouter
}

describe('knowledge-base route table', () => {
  it('renders a real section through the workspace outlet context', async () => {
    renderAt('/knowledge-bases/kb-1')

    // The workspace header and the section below it describe one corpus,
    // because the section reads it from the context rather than re-fetching.
    expect(await screen.findByRole('heading', { level: 1, name: 'Fraud KB' })).toBeInTheDocument()
    const overview = await screen.findByRole('region', {
      name: 'Where this knowledge base stands',
    })
    expect(
      within(overview).getByText(
        'This knowledge base is empty. Add documents or structured records to start.',
      ),
    ).toBeInTheDocument()
  })

  it('renders each section at its own address', async () => {
    renderAt('/knowledge-bases/kb-1/runs')

    expect(await screen.findByRole('button', { name: 'Start score-all' })).toBeInTheDocument()
  })

  // The section reports the intent; the route binding is what turns it into a
  // user-visible move, and only this test crosses that boundary.
  it('sends the empty-inventory action to Add data', async () => {
    const testRouter = renderAt('/knowledge-bases/kb-1/data')

    await userEvent.click(await screen.findByRole('button', { name: 'Stage a source' }))

    await waitFor(() => {
      expect(testRouter.state.location.pathname).toBe('/knowledge-bases/kb-1/add')
    })
    expect(await screen.findByText('Choose a source')).toBeInTheDocument()
  })

  it('returns to the library once the knowledge base is deleted', async () => {
    const testRouter = renderAt('/knowledge-bases/kb-1/settings')

    await userEvent.click(await screen.findByRole('button', { name: 'Delete knowledge base' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByRole('textbox'), 'Fraud KB')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete knowledge base' }))

    await waitFor(() => expect(deleteRequests()).toHaveLength(1))
    await waitFor(() => {
      expect(testRouter.state.location.pathname).toBe('/knowledge-bases')
    })
  })

  // Through the real `knowledgebases` element, so reverting it to a bare
  // `<Navigate to="/knowledge-bases">` — the query-dropping bug this split
  // fixed — fails here rather than passing unnoticed.
  it('carries a legacy address and its query string all the way to the section', async () => {
    const testRouter = renderAt('/knowledgebases?kb=kb-1&document=doc-2')

    await waitFor(() => {
      expect(testRouter.state.location.pathname).toBe('/knowledge-bases/kb-1/data')
      expect(testRouter.state.location.search).toBe('?document=doc-2')
    })
    expect(await screen.findByText('Document inventory')).toBeInTheDocument()
  })
})
