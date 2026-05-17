import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useIngestionStudioStore } from '../../stores/ingestionStudioStore'
import { KnowledgeBaseManagerPage } from '../KnowledgeBaseManagerPage'

function renderWithClient(node: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }): React.ReactElement {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  return render(node, { wrapper: Wrapper })
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
    allowed_content_types: ['text/plain', 'text/csv', 'application/json'],
    max_query_length: 10000,
    max_rag_question_length: 5000,
  },
  records: {
    feeds: [
      {
        name: 'claims_feed',
        record_type: 'claim_record',
        source: 'file_upload',
        id_field: 'claim_id',
        record_schema: {
          claim_id: { type: 'string', display: 'Claim ID', required: true },
          provider_npi: {
            type: 'string',
            display: 'Provider NPI',
            required: true,
            pattern: '^[0-9]{10}$',
          },
          billed_amount: { type: 'decimal', display: 'Billed Amount', required: true },
        },
        entities: [],
        relationships: [],
        observations: [],
      },
      {
        name: 'provider_push',
        record_type: 'provider_record',
        source: 'api_push',
        id_field: 'provider_npi',
        record_schema: {
          provider_npi: {
            type: 'string',
            display: 'Provider NPI',
            required: true,
            pattern: '^[0-9]{10}$',
          },
        },
        entities: [],
        relationships: [],
        observations: [],
      },
    ],
  },
  alerts: { thresholds: {} },
}

function installFetchMock({ recordsFail = false }: { recordsFail?: boolean } = {}) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()

    if (url.endsWith('/config/domain')) {
      return new Response(JSON.stringify(domainConfig), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }

    if (url.endsWith('/workflows')) {
      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }

    if (url.endsWith('/knowledgebases')) {
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 'kb-1',
              name: 'Fraud KB',
              description: 'Active backend shape',
              status: 'active',
              document_count: 0,
              entity_count: 2,
              relationship_count: 1,
              created_at: '2026-05-10T00:00:00Z',
            },
          ],
          total: 1,
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    }

    if (url.endsWith('/knowledgebases/kb-1')) {
      return new Response(
        JSON.stringify({
          id: 'kb-1',
          name: 'Fraud KB',
          description: 'Active backend shape',
          status: 'active',
          document_count: 0,
          entity_count: 2,
          relationship_count: 1,
          created_at: '2026-05-10T00:00:00Z',
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    }

    if (url.endsWith('/knowledgebases/kb-1/documents') && init?.method === 'POST') {
      return new Response(
        JSON.stringify({
          documents: [
            {
              knowledge_base_id: 'kb-1',
              source_document_id: 'doc-1',
              filename: 'policy.txt',
              status: 'registered',
              storage_key: null,
              uri: null,
              document_format: 'txt',
              created_at: '2026-05-17T00:00:00Z',
            },
          ],
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    }

    if (url.endsWith('/knowledgebases/kb-1/documents')) {
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 'doc-existing',
              knowledge_base_id: 'kb-1',
              filename: 'existing-policy.txt',
              content_type: 'text/plain',
              size_bytes: 1024,
              status: 'validated',
              created_at: '2026-05-11T00:00:00Z',
            },
          ],
          total: 1,
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    }

    if (url.endsWith('/records/kb-1/push')) {
      if (recordsFail) {
        return new Response(JSON.stringify({ detail: 'Records backend rejected the file.' }), {
          status: 422,
          headers: { 'content-type': 'application/json' },
        })
      }

      return new Response(
        JSON.stringify({
          knowledge_base_id: 'kb-1',
          feed_name: 'provider_push',
          record_type: 'provider_record',
          correlation_id: 'corr-1',
          accepted_count: 1,
          created_at: '2026-05-17T00:00:00Z',
        }),
        { status: 202, headers: { 'content-type': 'application/json' } },
      )
    }

    if (url.endsWith('/records/kb-1/files')) {
      return new Response(
        JSON.stringify({
          knowledge_base_id: 'kb-1',
          feed_name: 'claims_feed',
          record_type: 'claim_record',
          correlation_id: 'corr-file-1',
          accepted_count: 1,
          created_at: '2026-05-17T00:00:00Z',
        }),
        { status: 202, headers: { 'content-type': 'application/json' } },
      )
    }

    return new Response('{}', {
      status: 404,
      headers: { 'content-type': 'application/json' },
    })
  }) as unknown as typeof fetch
}

async function parseValidRecords() {
  await userEvent.click(screen.getByRole('radio', { name: /Structured Records/i }))
  await userEvent.selectOptions(screen.getByLabelText('Records feed'), 'provider_push')
  await userEvent.selectOptions(screen.getByLabelText('Records format'), 'CSV')
  await userEvent.type(
    screen.getByLabelText('Records content'),
    'provider_npi\n1234567890\n',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Parse records' }))
}

describe('KnowledgeBaseManagerPage Ingestion Studio', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    useIngestionStudioStore.getState().reset()
    installFetchMock()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('renders the Ingestion Studio shell and existing knowledge base', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByText('Ingestion Studio')).toBeInTheDocument()
    expect(await screen.findAllByText('Fraud KB')).toHaveLength(2)
    expect(screen.getByText('Knowledge base')).toBeInTheDocument()
    expect(screen.getByText('existing-policy.txt')).toBeInTheDocument()
  })

  it('submits documents and stores a receipt in the timeline', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Submit documents' }))

    expect(await screen.findByText('1 document accepted.')).toBeInTheDocument()
  })

  it('parses and submits records through a configured feed', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await parseValidRecords()
    await userEvent.click(screen.getByRole('button', { name: 'Submit records' }))

    expect(await screen.findByText('1 records accepted for provider_push.')).toBeInTheDocument()
  })

  it('uploads configured file-upload records feeds through the records file endpoint', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Structured Records/i }))
    await userEvent.selectOptions(screen.getByLabelText('Records feed'), 'claims_feed')
    await userEvent.upload(
      screen.getByLabelText('Records file'),
      new File(['claim_id,provider_npi,billed_amount\nc1,1234567890,99.50\n'], 'claims.csv', {
        type: 'text/csv',
      }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Parse records' }))
    await userEvent.click(screen.getByRole('button', { name: 'Submit records' }))

    expect(await screen.findByText('1 records accepted for claims_feed.')).toBeInTheDocument()
    const recordsFileCall = vi
      .mocked(fetch)
      .mock.calls.find(([input]) => input.toString().endsWith('/records/kb-1/files'))
    expect(recordsFileCall).toBeDefined()
    expect(recordsFileCall?.[1]?.body).toBeInstanceOf(FormData)
  })

  it('requires re-parsing after changing a records file upload draft', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Structured Records/i }))
    await userEvent.selectOptions(screen.getByLabelText('Records feed'), 'claims_feed')
    await userEvent.upload(
      screen.getByLabelText('Records file'),
      new File(['claim_id,provider_npi,billed_amount\nc1,1234567890,99.50\n'], 'claims.csv', {
        type: 'text/csv',
      }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Parse records' }))
    expect(screen.getByRole('button', { name: 'Submit records' })).toBeEnabled()

    await userEvent.upload(
      screen.getByLabelText('Records file'),
      new File(['claim_id,provider_npi,billed_amount\nc2,1234567890,101.25\n'], 'claims-2.csv', {
        type: 'text/csv',
      }),
    )

    expect(screen.getByRole('button', { name: 'Submit records' })).toBeDisabled()
  })

  it('requires re-parsing after editing pasted api-push records', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await parseValidRecords()
    expect(screen.getByRole('button', { name: 'Submit records' })).toBeEnabled()

    await userEvent.type(screen.getByLabelText('Records content'), '1')

    expect(screen.getByRole('button', { name: 'Submit records' })).toBeDisabled()
  })

  it('shows client validation before records submit', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Structured Records/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Submit records' }))

    expect(await screen.findByText('Select a structured records feed before submitting.')).toBeInTheDocument()
  })

  it('shows backend records errors in the validation panel', async () => {
    installFetchMock({ recordsFail: true })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await parseValidRecords()
    await userEvent.click(screen.getByRole('button', { name: 'Submit records' }))

    expect(await screen.findByText('Backend response')).toBeInTheDocument()
    expect(screen.getByText('Records backend rejected the file.')).toBeInTheDocument()
  })

  it('preserves successful document receipt when records validation fails', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Submit documents' }))
    await screen.findByText('1 document accepted.')

    await userEvent.click(screen.getByRole('radio', { name: /Structured Records/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Submit records' }))

    await waitFor(() => {
      expect(screen.getByText('1 document accepted.')).toBeInTheDocument()
      expect(screen.getByText('Select a structured records feed before submitting.')).toBeInTheDocument()
    })
  })
})
