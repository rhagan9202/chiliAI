import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { useEffect } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DataSection } from '../DataSection'

type MockDocument = {
  id: string
  knowledge_base_id: string
  filename: string
  content_type: string
  size_bytes: number
  /** Registration status; the durable lifecycle lives in `current_status`. */
  status: string
  current_status?: string | null
  last_error?: string | null
  dropped_entity_count?: number
  dropped_relationship_count?: number
  created_at: string
  warning_count: number
  warning_reasons: string[]
}

const defaultDocuments: MockDocument[] = [
  {
    id: 'doc-1',
    knowledge_base_id: 'kb-1',
    filename: 'policy.txt',
    content_type: 'text/plain',
    size_bytes: 1024,
    status: 'validated',
    current_status: 'validated',
    created_at: '2026-08-01T00:00:00Z',
    warning_count: 0,
    warning_reasons: [],
  },
  {
    id: 'doc-2',
    knowledge_base_id: 'kb-1',
    filename: 'resume.txt',
    content_type: 'text/plain',
    size_bytes: 512,
    status: 'validated',
    current_status: 'extracted_empty',
    created_at: '2026-08-02T00:00:00Z',
    warning_count: 0,
    warning_reasons: [],
  },
]

// A ref assigned from an effect, not a bare module-level variable reassigned
// during render — react-hooks/react-compiler flags render-time mutation of
// outer-scope state as an impurity (see useActiveKnowledgeBase.test.tsx's
// locationRef for the same pattern).
const observedSearchRef: { current: string } = { current: '' }

function SearchProbe() {
  const location = useLocation()
  useEffect(() => {
    observedSearchRef.current = location.search
  }, [location])
  return null
}

function renderSection(initialEntry: string, onStageSource = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route
              path="/knowledge-bases/:kbId/data"
              element={
                <>
                  {children}
                  <SearchProbe />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )
  }

  const result = render(
    <DataSection knowledgeBaseId="kb-1" onStageSource={onStageSource} />,
    { wrapper: Wrapper },
  )
  return { ...result, onStageSource }
}

/** URLs of every DELETE issued — destructive actions must not fire unconfirmed. */
function deleteRequests(): string[] {
  const mock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
  return mock.mock.calls
    .filter((call) => (call[1] as RequestInit | undefined)?.method === 'DELETE')
    .map((call) => String(call[0]))
}

const originalFetch = globalThis.fetch

let documents: MockDocument[] = defaultDocuments
let previewTextByDocument: Record<string, string> = {}
let previewFail = false
let previewDelayMs = 0

beforeEach(() => {
  documents = defaultDocuments
  previewTextByDocument = {}
  previewFail = false
  previewDelayMs = 0

  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()

    if (init?.method === 'DELETE') {
      return new Response(null, { status: 204 })
    }

    if (url.includes('/documents/') && url.includes('/preview')) {
      if (previewDelayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, previewDelayMs))
      }
      if (previewFail) {
        return new Response(JSON.stringify({ detail: 'Preview failed' }), {
          status: 415,
          headers: { 'content-type': 'application/json' },
        })
      }
      const documentId = url.split('/documents/')[1].split('/')[0]
      const document = documents.find((item) => item.id === documentId)
      const previewText = previewTextByDocument[documentId] ?? `preview of ${documentId}`
      return new Response(
        JSON.stringify({
          knowledge_base_id: 'kb-1',
          document_id: documentId,
          filename: document?.filename ?? 'policy.txt',
          preview_text: previewText,
          line_count: previewText.length === 0 ? 0 : previewText.split('\n').length,
          truncated: false,
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    }

    if (url.includes('/documents')) {
      const status = new URL(url, 'http://localhost').searchParams.get('status')
      const items = status ? documents.filter((item) => item.current_status === status) : documents
      return new Response(JSON.stringify({ items, total: items.length }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }

    throw new Error(`unexpected request: ${url}`)
  }) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

describe('DataSection', () => {
  it('opens the document named by ?document=', async () => {
    renderSection('/knowledge-bases/kb-1/data?document=doc-2')

    await waitFor(() => {
      expect(screen.getByText('preview of doc-2')).toBeInTheDocument()
    })
  })

  it('falls back to the first document when ?document= names one that is not listed', async () => {
    renderSection('/knowledge-bases/kb-1/data?document=doc-gone')

    await waitFor(() => {
      expect(screen.getByText('preview of doc-1')).toBeInTheDocument()
    })
  })

  it('writes the selection into the URL so it survives a reload', async () => {
    renderSection('/knowledge-bases/kb-1/data')

    await waitFor(() => expect(screen.getByText('resume.txt')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /resume\.txt/ }))

    await waitFor(() => {
      expect(observedSearchRef.current).toBe('?document=doc-2')
    })
  })

  it('filters by the durable lifecycle status', async () => {
    renderSection('/knowledge-bases/kb-1/data')

    await waitFor(() => expect(screen.getByText('policy.txt')).toBeInTheDocument())
    await userEvent.selectOptions(
      screen.getByLabelText('Filter documents by status'),
      'extracted_empty',
    )

    await waitFor(() => {
      expect(screen.queryByText('policy.txt')).not.toBeInTheDocument()
      expect(screen.getByText('resume.txt')).toBeInTheDocument()
    })
  })

  it('confirms before removing a document', async () => {
    renderSection('/knowledge-bases/kb-1/data?document=doc-1')

    await waitFor(() => expect(screen.getByText('policy.txt')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Remove document' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('policy.txt')
  })

  // Rehomed from KnowledgeBaseManagerPage.test.tsx.
  it('leaves a document in place when its removal is cancelled', async () => {
    renderSection('/knowledge-bases/kb-1/data?document=doc-1')

    await waitFor(() => expect(screen.getByText('policy.txt')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Remove document' }))

    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(deleteRequests()).toHaveLength(0)
    expect(screen.getByText('policy.txt')).toBeInTheDocument()
  })

  // Rehomed: reasons used to be reachable only by hover (a `title`) or by
  // selecting the row. Neither is discoverable, and neither works on touch.
  it('shows a warning chip and its reasons behind an explicit toggle', async () => {
    documents = [
      {
        ...defaultDocuments[0],
        warning_count: 2,
        warning_reasons: [
          'csv.ragged_row: Row has 4 field(s) but the header declares 3',
          'entity claim-1: normalization_failed: amount',
        ],
      },
    ]
    renderSection('/knowledge-bases/kb-1/data')

    const documentRow = await screen.findByRole('button', { name: /policy\.txt/ })
    expect(within(documentRow).getByText('2 warnings')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Show 2 warnings' }))
    const reasons = await screen.findByTestId('document-warning-reasons')
    expect(within(reasons).getByText(/csv\.ragged_row/)).toBeInTheDocument()
    expect(within(reasons).getByText(/normalization_failed/)).toBeInTheDocument()
  })

  // Rehomed: a document that produced no entities used to read as a green
  // "ready", because the row showed the registration status.
  it('renders the durable lifecycle state, not the registration status', async () => {
    documents = [
      {
        ...defaultDocuments[0],
        id: 'doc-empty',
        filename: 'resume-like.txt',
        status: 'ready',
        current_status: 'extracted_empty',
      },
    ]
    renderSection('/knowledge-bases/kb-1/data')

    const row = await screen.findByRole('button', { name: /resume-like\.txt/ })
    expect(within(row).getByText('No entities')).toBeInTheDocument()
    expect(within(row).queryByText('Validated')).not.toBeInTheDocument()
  })

  // Rehomed.
  it('shows the failure reason on a failed document without any clicks', async () => {
    documents = [
      {
        ...defaultDocuments[0],
        id: 'doc-failed',
        filename: 'broken.json',
        status: 'ready',
        current_status: 'failed',
        last_error: 'Parser gave up: unexpected token at line 3',
      },
    ]
    renderSection('/knowledge-bases/kb-1/data')

    const row = await screen.findByRole('button', { name: /broken\.json/ })
    expect(within(row).getByText('Failed')).toBeInTheDocument()
    expect(within(row).getByText(/Parser gave up/)).toBeInTheDocument()
  })

  // Rehomed: exact counts only — how many were kept is not in this payload.
  it('reports dropped entities and relationships as exact counts', async () => {
    documents = [
      {
        ...defaultDocuments[0],
        id: 'doc-drops',
        filename: 'partial.json',
        current_status: 'validated',
        dropped_entity_count: 3,
        dropped_relationship_count: 2,
      },
    ]
    renderSection('/knowledge-bases/kb-1/data')

    const row = await screen.findByRole('button', { name: /partial\.json/ })
    expect(within(row).getByText(/3 entities dropped/)).toBeInTheDocument()
    expect(within(row).getByText(/2 relationships dropped/)).toBeInTheDocument()
  })

  // Rehomed (UXA-305): a brand-new knowledge base used to stack cards that all
  // said the same thing. The inventory says it once, with a way out.
  it('states an empty inventory once, with an action', async () => {
    documents = []
    const { onStageSource } = renderSection('/knowledge-bases/kb-1/data')

    expect(await screen.findByText('No documents yet')).toBeInTheDocument()
    expect(screen.queryByText('No document selected')).not.toBeInTheDocument()
    expect(screen.queryByText('Document preview')).not.toBeInTheDocument()

    // The action used to scroll the staging form into view on the one-page
    // layout; Add data is a real address now, so the section reports the
    // intent and its route binding navigates.
    await userEvent.click(screen.getByRole('button', { name: 'Stage a source' }))
    expect(onStageSource).toHaveBeenCalledTimes(1)
  })

  // Rehomed.
  it('states an empty document preview when the preview text is blank', async () => {
    previewTextByDocument = { 'doc-1': '' }
    renderSection('/knowledge-bases/kb-1/data?document=doc-1')

    expect(await screen.findByText('No preview text returned')).toBeInTheDocument()
  })

  // Rehomed.
  it('states a failed document preview rather than an empty one', async () => {
    previewFail = true
    renderSection('/knowledge-bases/kb-1/data?document=doc-1')

    expect(
      await screen.findByText('Document preview could not be loaded from the API.'),
    ).toBeInTheDocument()
  })

  // Rehomed.
  it('says the preview is loading while it is in flight', async () => {
    previewDelayMs = 25
    renderSection('/knowledge-bases/kb-1/data?document=doc-1')

    expect(await screen.findByText('Loading document preview')).toBeInTheDocument()
    expect(await screen.findByText('preview of doc-1')).toBeInTheDocument()
  })

  // Rehomed: the line count and filename name what is on screen.
  it('names the document and its line count above the preview', async () => {
    previewTextByDocument = { 'doc-1': 'Section 1\nSection 2\nSection 3' }
    renderSection('/knowledge-bases/kb-1/data?document=doc-1')

    expect(await screen.findByText(/3 lines from policy\.txt/)).toBeInTheDocument()
  })
})
