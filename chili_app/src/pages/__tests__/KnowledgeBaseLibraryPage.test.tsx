import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

/** Created before domains were stamped; scoping must not treat it as foreign. */
const legacyKb = {
  ...medicareKb,
  id: 'kb-3',
  name: 'Legacy KB',
  description: 'No domain stamp at all',
  domain: null,
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

let listedKnowledgeBases: unknown[] = [medicareKb, housingKb]

beforeEach(() => {
  listedKnowledgeBases = [medicareKb, housingKb]
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    const json = (payload: unknown) =>
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })

    if (url.endsWith('/config/domain')) return json(domainConfig)
    if (url.endsWith('/knowledgebases')) {
      return json({ items: listedKnowledgeBases, total: listedKnowledgeBases.length })
    }
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

describe('KnowledgeBaseLibraryPage', () => {
  it('links each card to that knowledge base’s workspace', async () => {
    renderAt('/knowledge-bases')

    const card = await screen.findByRole('link', { name: /Fraud KB/ })
    expect(card).toHaveAttribute('href', '/knowledge-bases/kb-1')
  })

  // Rehomed from KnowledgeBaseManagerPage.test.tsx: the destination answered to
  // three names at once — "Knowledge Bases" in the nav, "Ingestion Studio" as
  // the title, "Ingestion Control" as the eyebrow.
  it('calls the destination what the sidebar calls it', async () => {
    renderAt('/knowledge-bases')

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' }),
    ).toBeInTheDocument()
    expect(screen.queryByText(/ingestion studio/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/ingestion control/i)).not.toBeInTheDocument()
  })

  it('scopes to the active domain and reveals the rest on demand', async () => {
    renderAt('/knowledge-bases')

    await waitFor(() => expect(screen.getByText('Fraud KB')).toBeInTheDocument())
    expect(screen.queryByText('Housing KB')).not.toBeInTheDocument()

    await userEvent.click(screen.getByTestId('kb-show-all-domains-toggle'))
    expect(screen.getByText('Housing KB')).toBeInTheDocument()

    // Rehomed: scoping back down hides the other domain again.
    await userEvent.click(screen.getByTestId('kb-show-all-domains-toggle'))
    await waitFor(() => expect(screen.queryByText('Housing KB')).not.toBeInTheDocument())
  })

  // Rehomed from KnowledgeBaseManagerPage.test.tsx: a knowledge base created
  // before domains were stamped has no domain to mismatch, so scoping keeps it.
  it('keeps legacy knowledge bases without a domain stamp in the scoped list', async () => {
    listedKnowledgeBases = [legacyKb, housingKb]
    renderAt('/knowledge-bases')

    expect(await screen.findByText('Legacy KB')).toBeInTheDocument()
    expect(screen.queryByText('Housing KB')).not.toBeInTheDocument()
    expect(screen.getByTestId('kb-show-all-domains-toggle')).toHaveTextContent(
      'Show all domains (1 hidden)',
    )
  })

  it('redirects a legacy ?kb= address to that workspace', async () => {
    const testRouter = renderAt('/knowledge-bases?kb=kb-1')

    await waitFor(() => {
      expect(testRouter.state.location.pathname).toBe('/knowledge-bases/kb-1')
    })
  })

  it('redirects a legacy ?kb=&document= address into the data section', async () => {
    const testRouter = renderAt('/knowledge-bases?kb=kb-1&document=doc-2')

    await waitFor(() => {
      expect(testRouter.state.location.pathname).toBe('/knowledge-bases/kb-1/data')
      expect(testRouter.state.location.search).toBe('?document=doc-2')
    })
  })
})
