import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { KnowledgeBaseLibraryPage } from '../KnowledgeBaseLibraryPage'
import { KnowledgeBaseWorkspacePage } from '../KnowledgeBaseWorkspacePage'

const medicareKb = {
  id: 'kb-1',
  name: 'Fraud KB',
  description: 'Active corpus',
  status: 'ready',
  document_count: 8,
  entity_count: 53,
  relationship_count: 21,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-14T00:00:00Z',
  domain: 'medicare_fraud',
}

const housingKb = {
  ...medicareKb,
  id: 'kb-2',
  name: 'Housing KB',
  description: 'Another domain',
  domain: 'department_air_force_housing',
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

beforeEach(() => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    const json = (payload: unknown) =>
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })

    if (url.endsWith('/config/domain')) return json(domainConfig)
    if (url.split('?')[0].endsWith('/knowledgebases')) return json({ items: [medicareKb, housingKb], total: 2 })
    if (url.endsWith('/knowledgebases/kb-1')) return json(medicareKb)
    if (url.endsWith('/knowledgebases/kb-2')) return json(housingKb)
    if (url.endsWith('/knowledgebases/kb-missing')) {
      return new Response(JSON.stringify({ detail: 'not found' }), { status: 404 })
    }
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
  const testRouter = createMemoryRouter(
    [
      { path: '/knowledge-bases', element: <KnowledgeBaseLibraryPage /> },
      {
        path: '/knowledge-bases/:kbId',
        element: <KnowledgeBaseWorkspacePage />,
        children: [
          { index: true, element: <p>Overview body</p> },
          { path: 'add', element: <p>Add body</p> },
          { path: 'data', element: <p>Data body</p> },
          { path: 'runs', element: <p>Runs body</p> },
          { path: 'settings', element: <p>Settings body</p> },
        ],
      },
    ],
    { initialEntries: [initialEntry] },
  )

  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={testRouter} />
    </QueryClientProvider>,
  )
  return testRouter
}

describe('KnowledgeBaseWorkspacePage', () => {
  it('names the knowledge base and states its digest', async () => {
    renderAt('/knowledge-bases/kb-1')

    expect(await screen.findByRole('heading', { level: 1, name: 'Fraud KB' })).toBeInTheDocument()
    expect(screen.getByText('8 documents')).toBeInTheDocument()
    expect(screen.getByText('53 entities')).toBeInTheDocument()
  })

  // Rehomed from KnowledgeBaseManagerPage.test.tsx: the selected-KB summary
  // card carried the provenance badge. The workspace header is where a corpus
  // now says which domain it was built under — warn only, nothing disabled.
  it('flags a knowledge base built under another domain without blocking it', async () => {
    renderAt('/knowledge-bases/kb-2')

    expect(await screen.findByRole('heading', { level: 1, name: 'Housing KB' })).toBeInTheDocument()
    expect(screen.getByTestId('kb-domain-mismatch')).toHaveTextContent(
      'Created under department_air_force_housing',
    )
    expect(
      screen.getByRole('navigation', { name: 'Knowledge base sections' }),
    ).toBeInTheDocument()
  })

  it('shows no provenance badge when the knowledge base matches the active domain', async () => {
    renderAt('/knowledge-bases/kb-1')

    await screen.findByRole('heading', { level: 1, name: 'Fraud KB' })
    expect(screen.queryByTestId('kb-domain-mismatch')).not.toBeInTheDocument()
    expect(screen.queryByTestId('kb-domain-unknown')).not.toBeInTheDocument()
  })

  it('offers every section as a link', async () => {
    renderAt('/knowledge-bases/kb-1')

    const tabs = await screen.findByRole('navigation', { name: 'Knowledge base sections' })
    expect(within(tabs).getByRole('link', { name: 'Overview' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1',
    )
    expect(within(tabs).getByRole('link', { name: 'Add data' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/add',
    )
    expect(within(tabs).getByRole('link', { name: 'Data' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/data',
    )
    expect(within(tabs).getByRole('link', { name: 'Runs' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/runs',
    )
    expect(within(tabs).getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/settings',
    )
  })

  it('marks only the section on screen as current', async () => {
    renderAt('/knowledge-bases/kb-1/runs')

    const tabs = await screen.findByRole('navigation', { name: 'Knowledge base sections' })
    expect(within(tabs).getByRole('link', { name: 'Runs' })).toHaveAttribute('aria-current', 'page')
    // Without `end`, Overview would read as current on every section, because
    // every section path starts with the overview path.
    expect(within(tabs).getByRole('link', { name: 'Overview' })).not.toHaveAttribute('aria-current')
  })

  it('renders the section body for the address', async () => {
    renderAt('/knowledge-bases/kb-1/settings')

    expect(await screen.findByText('Settings body')).toBeInTheDocument()
  })

  it('says so for an unknown id instead of showing another knowledge base', async () => {
    renderAt('/knowledge-bases/kb-missing')

    expect(await screen.findByText(/could not be opened/i)).toBeInTheDocument()
    expect(screen.queryByText('Fraud KB')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to knowledge bases' })).toHaveAttribute(
      'href',
      '/knowledge-bases',
    )
  })
})
