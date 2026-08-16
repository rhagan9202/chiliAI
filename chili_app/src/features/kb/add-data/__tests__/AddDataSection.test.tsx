import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useIngestionDraftStore } from '../../../../stores/ingestionDraftStore'
import { AddDataSection } from '../AddDataSection'

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
    allowed_content_types: ['text/plain', 'text/csv', 'application/json'],
    max_query_length: 10000,
    max_rag_question_length: 5000,
  },
  records: { feeds: [] },
  alerts: { thresholds: {} },
}

function renderSection(onSubmitted = vi.fn()) {
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

  const result = render(
    <AddDataSection knowledgeBaseId="kb-1" onSubmitted={onSubmitted} />,
    { wrapper: Wrapper },
  )
  return { ...result, onSubmitted }
}

const originalFetch = globalThis.fetch

beforeEach(() => {
  useIngestionDraftStore.getState().reset()
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.endsWith('/config/domain')) {
      return new Response(JSON.stringify(domainConfig), {
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

describe('AddDataSection', () => {
  it('will not submit with nothing staged, and says what is missing', async () => {
    renderSection()

    const submit = await screen.findByRole('button', { name: 'Run ingestion' })
    expect(submit).toBeDisabled()
    expect(screen.getByText('Select source type')).toBeInTheDocument()
  })

  it('stages documents into the draft for this knowledge base only', async () => {
    renderSection()

    await userEvent.click(await screen.findByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files', { exact: true }),
      new File(['{}'], 'claim.json', { type: 'application/json' }),
    )

    await waitFor(() => {
      const drafts = useIngestionDraftStore.getState().draftsByKb
      expect(drafts['kb-1'].pendingFiles.map((file) => file.name)).toEqual(['claim.json'])
      expect(drafts['kb-2']).toBeUndefined()
    })
  })

  it('enables submit once documents are staged and pass client validation', async () => {
    renderSection()

    await userEvent.click(await screen.findByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files', { exact: true }),
      new File(['{}'], 'claim.json', { type: 'application/json' }),
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeEnabled()
    })
  })
})
