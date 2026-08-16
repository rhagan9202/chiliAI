import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { useEffect } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DataSection } from '../DataSection'

const documents = [
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

function renderSection(initialEntry: string) {
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

  return render(<DataSection knowledgeBaseId="kb-1" onStageSource={vi.fn()} />, {
    wrapper: Wrapper,
  })
}

const originalFetch = globalThis.fetch

beforeEach(() => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()

    if (url.includes('/documents/') && url.includes('/preview')) {
      const documentId = url.split('/documents/')[1].split('/')[0]
      return new Response(
        JSON.stringify({
          knowledge_base_id: 'kb-1',
          document_id: documentId,
          filename: documentId === 'doc-2' ? 'resume.txt' : 'policy.txt',
          preview_text: `preview of ${documentId}`,
          line_count: 1,
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
})
