import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useIngestionStudioStore } from '../../stores/ingestionStudioStore'
import { KnowledgeBaseManagerPage } from '../KnowledgeBaseManagerPage'

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}))

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router')
  return {
    ...actual,
    useNavigate: () => routerMocks.navigate,
  }
})

function renderWithClient(node: React.ReactElement, initialEntries?: string[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }): React.ReactElement {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
      </QueryClientProvider>
    )
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

type UploadOutcome = { status: number; body: unknown }

type MockKnowledgeBase = {
  id: string
  name: string
  description: string
  status: string
  document_count: number
  entity_count: number
  relationship_count: number
  created_at: string
  domain: string | null
}

/** In-scope KB for the mocked active domain (medicare_fraud). */
const medicareKb: MockKnowledgeBase = {
  id: 'kb-1',
  name: 'Fraud KB',
  description: 'Active backend shape',
  status: 'active',
  document_count: 0,
  entity_count: 2,
  relationship_count: 1,
  created_at: '2026-05-10T00:00:00Z',
  domain: 'medicare_fraud',
}

/** Second in-scope KB, listed first, so deep-link selection has to beat it. */
const secondMedicareKb: MockKnowledgeBase = {
  id: 'kb-3',
  name: 'Demo KB',
  description: 'Sorts ahead of Fraud KB in the list',
  status: 'ready',
  document_count: 3,
  entity_count: 9,
  relationship_count: 4,
  created_at: '2026-05-14T00:00:00Z',
  domain: 'medicare_fraud',
}

/** Out-of-scope KB created under a different domain. */
const housingKb: MockKnowledgeBase = {
  id: 'kb-2',
  name: 'Housing KB',
  description: 'Corpus created under another domain',
  status: 'ready',
  document_count: 1,
  entity_count: 5,
  relationship_count: 2,
  created_at: '2026-05-12T00:00:00Z',
  domain: 'af_housing',
}

/**
 * Minimal XMLHttpRequest stub. Uploads (documents + records files) go through
 * XHR so byte-level progress can be reported; this stub resolves them with the
 * same canned responses the fetch mock returns for the corresponding routes.
 */
function installXhrMock({
  documentFail = false,
  recordsFail = false,
}: {
  documentFail?: boolean
  recordsFail?: boolean
} = {}) {
  function outcomeFor(url: string): UploadOutcome {
    if (url.includes('/knowledgebases/kb-1/documents')) {
      if (documentFail) {
        return { status: 415, body: { detail: 'Unsupported document content type.' } }
      }
      return {
        status: 200,
        body: {
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
        },
      }
    }

    if (url.includes('/records/kb-1/files')) {
      if (recordsFail) {
        return { status: 422, body: { detail: 'Records backend rejected the file.' } }
      }
      return {
        status: 202,
        body: {
          knowledge_base_id: 'kb-1',
          feed_name: 'claims_feed',
          record_type: 'claim_record',
          correlation_id: 'corr-file-1',
          accepted_count: 1,
          duplicate: false,
          duplicate_count: 0,
          rejected_count: 0,
          created_at: '2026-05-17T00:00:00Z',
        },
      }
    }

    return { status: 404, body: {} }
  }

  class FakeUploadXhr {
    url = ''
    withCredentials = false
    responseType = ''
    status = 0
    response: unknown = null
    responseText = ''
    readonly upload: { onprogress: ((event: ProgressEvent) => void) | null } = {
      onprogress: null,
    }
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    onabort: (() => void) | null = null

    open(_method: string, url: string): void {
      this.url = url
    }

    send(): void {
      const outcome = outcomeFor(this.url)
      this.upload.onprogress?.({
        lengthComputable: true,
        loaded: 100,
        total: 100,
      } as ProgressEvent)
      this.status = outcome.status
      this.response = outcome.body
      queueMicrotask(() => this.onload?.())
    }
  }

  globalThis.XMLHttpRequest = FakeUploadXhr as unknown as typeof XMLHttpRequest
}

function installFetchMock({
  documentFail = false,
  recordsFail = false,
  structuredRecordsFail = false,
  kbDomain = null,
  kbItems,
}: {
  documentFail?: boolean
  recordsFail?: boolean
  structuredRecordsFail?: boolean
  /** `domain` stamped on the mocked knowledge base (null = legacy/unknown). */
  kbDomain?: string | null
  /** Full KB list override; defaults to the single kb-1 stamped with `kbDomain`. */
  kbItems?: MockKnowledgeBase[]
} = {}) {
  const knowledgeBaseItems = kbItems ?? [{ ...medicareKb, domain: kbDomain }]
  installXhrMock({ documentFail, recordsFail })
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()

    if (url.endsWith('/config/domain')) {
      return new Response(JSON.stringify(domainConfig), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }

    if (url.includes('/workflows')) {
      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }

    if (url.endsWith('/knowledgebases')) {
      return new Response(
        JSON.stringify({ items: knowledgeBaseItems, total: knowledgeBaseItems.length }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    }

    const detailMatch = url.match(/\/knowledgebases\/([^/]+)$/)
    if (detailMatch) {
      const item = knowledgeBaseItems.find((kb) => kb.id === detailMatch[1])
      if (item) {
        return new Response(JSON.stringify(item), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      }
    }

    if (url.endsWith('/knowledgebases/kb-1/documents') && init?.method === 'POST') {
      if (documentFail) {
        return new Response(
          JSON.stringify({ detail: 'Unsupported document content type.' }),
          { status: 415, headers: { 'content-type': 'application/json' } },
        )
      }

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
              warning_count: 2,
              warning_reasons: [
                'csv.ragged_row: Row has 4 field(s) but the header declares 3',
                'entity claim-1: normalization_failed: amount',
              ],
            },
          ],
          total: 1,
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    }

    if (/\/knowledgebases\/[^/]+\/documents$/.test(url)) {
      return new Response(JSON.stringify({ items: [], total: 0 }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }

    if (url.endsWith('/records/kb-1/push')) {
      if (structuredRecordsFail) {
        return new Response(
          JSON.stringify({
            detail: [
              { loc: ['body', 'rows', 0, 'provider_npi'], msg: 'Field required' },
            ],
          }),
          { status: 422, headers: { 'content-type': 'application/json' } },
        )
      }

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

function getStepperItem(stepLabel: string): HTMLLIElement {
  const item = screen
    .getAllByRole('listitem')
    .find((li) => within(li).queryByText(stepLabel))
  if (!item) {
    throw new Error(`Stepper item with label "${stepLabel}" not found`)
  }
  return item as HTMLLIElement
}

describe('KnowledgeBaseManagerPage Ingestion Studio', () => {
  const originalFetch = globalThis.fetch
  const originalXhr = globalThis.XMLHttpRequest

  beforeEach(() => {
    useIngestionStudioStore.getState().reset()
    routerMocks.navigate.mockReset()
    installFetchMock()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    globalThis.XMLHttpRequest = originalXhr
    vi.restoreAllMocks()
  })

  it('renders the Ingestion Studio shell and existing knowledge base', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByText('Ingestion Studio')).toBeInTheDocument()
    expect(await screen.findAllByText('Fraud KB')).toHaveLength(2)
    expect(screen.getByText('Knowledge base')).toBeInTheDocument()
    expect(screen.getByText('existing-policy.txt')).toBeInTheDocument()
  })

  it('warns without blocking when the knowledge base was created under another domain', async () => {
    // Active domain in the mocked config is medicare_fraud.
    installFetchMock({ kbDomain: 'food_supply_chain' })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')

    // Scoped by default: the foreign-domain KB is hidden until revealed.
    expect(screen.queryByRole('button', { name: /fraud kb/i })).not.toBeInTheDocument()
    await userEvent.click(
      screen.getByRole('button', { name: 'Show all domains (1 hidden)' }),
    )

    // Badge on the KB list entry and on the selected-KB summary card.
    expect(await screen.findAllByTestId('kb-domain-mismatch')).toHaveLength(2)
    expect(screen.getAllByText('Created under food_supply_chain')).toHaveLength(2)

    // Banner note on the summary card.
    const note = screen.getByTestId('kb-domain-mismatch-note')
    expect(note).toHaveTextContent('created under the "food_supply_chain" domain')
    expect(note).toHaveTextContent('All actions remain available.')

    // Warn only — the KB stays selectable and deletable.
    expect(screen.getByRole('button', { name: /fraud kb/i })).toBeEnabled()
    expect(
      screen.getByRole('button', { name: /delete selected knowledge base/i }),
    ).toBeEnabled()
  })

  it('shows no domain badge when the knowledge base matches the active domain', async () => {
    installFetchMock({ kbDomain: 'medicare_fraud' })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await screen.findAllByText('Fraud KB')

    expect(screen.queryByTestId('kb-domain-mismatch')).not.toBeInTheDocument()
    expect(screen.queryByTestId('kb-domain-mismatch-note')).not.toBeInTheDocument()
    expect(screen.queryByTestId('kb-domain-unknown')).not.toBeInTheDocument()
  })

  it('renders a tolerated unknown state for a legacy knowledge base without a domain', async () => {
    // Default mock leaves kbDomain null (legacy KB created before stamping).
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await screen.findAllByText('Fraud KB')

    // List entry + summary card each show the subtle unknown chip, no warning.
    expect(screen.getAllByTestId('kb-domain-unknown')).toHaveLength(2)
    expect(screen.queryByTestId('kb-domain-mismatch')).not.toBeInTheDocument()
    expect(screen.queryByTestId('kb-domain-mismatch-note')).not.toBeInTheDocument()
  })

  it('hides knowledge bases from other domains by default and reveals them with the toggle', async () => {
    installFetchMock({ kbItems: [medicareKb, housingKb] })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await screen.findAllByText('Fraud KB')

    // Scoped default: the other-domain KB is hidden, with an accurate count.
    expect(screen.queryByText('Housing KB')).not.toBeInTheDocument()
    await userEvent.click(
      screen.getByRole('button', { name: 'Show all domains (1 hidden)' }),
    )

    expect(await screen.findByText('Housing KB')).toBeInTheDocument()

    // Scoping back down hides it again.
    await userEvent.click(screen.getByRole('button', { name: 'Scope to active domain' }))
    await waitFor(() => expect(screen.queryByText('Housing KB')).not.toBeInTheDocument())
  })

  it('keeps legacy null-domain knowledge bases visible in the scoped list', async () => {
    installFetchMock({ kbItems: [{ ...medicareKb, domain: null }, housingKb] })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await screen.findAllByText('Fraud KB')

    // Legacy KB stays visible with its unknown badge; the foreign KB is hidden.
    expect(screen.getAllByTestId('kb-domain-unknown')).toHaveLength(2)
    expect(screen.queryByText('Housing KB')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Show all domains (1 hidden)' }),
    ).toBeInTheDocument()
  })

  it('auto-selects the first in-scope knowledge base even when another domain sorts first', async () => {
    installFetchMock({ kbItems: [housingKb, medicareKb] })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')

    // List row + selected-KB summary both show the in-scope KB.
    expect(await screen.findAllByText('Fraud KB')).toHaveLength(2)
    expect(screen.queryByText('Housing KB')).not.toBeInTheDocument()

    // No detail/documents/workflows request ever targeted the out-of-scope KB.
    const requestedUrls = vi
      .mocked(globalThis.fetch)
      .mock.calls.map((call) => String(call[0]))
    expect(requestedUrls.some((requestedUrl) => requestedUrl.includes('kb-2'))).toBe(false)
  })

  it('honors a ?kb= deep-link when that knowledge base is not first in the list', async () => {
    installFetchMock({ kbItems: [secondMedicareKb, medicareKb] })
    renderWithClient(<KnowledgeBaseManagerPage />, ['/knowledge-bases?kb=kb-1'])

    await screen.findByText('Ingestion Studio')

    // List row + selected-KB summary both show the deep-linked KB, not the
    // first-listed one.
    expect(await screen.findAllByText('Fraud KB')).toHaveLength(2)
    expect(screen.getAllByText('Demo KB')).toHaveLength(1)

    // No detail/documents/workflows request ever targeted the first-listed KB.
    const requestedUrls = vi
      .mocked(globalThis.fetch)
      .mock.calls.map((call) => String(call[0]))
    expect(requestedUrls.some((requestedUrl) => requestedUrl.includes('kb-3'))).toBe(false)
  })

  it('falls back to auto-select when the ?kb= deep-link is unknown', async () => {
    installFetchMock()
    renderWithClient(<KnowledgeBaseManagerPage />, ['/knowledge-bases?kb=does-not-exist'])

    await screen.findByText('Ingestion Studio')
    expect(await screen.findAllByText('Fraud KB')).toHaveLength(2)
  })

  it('returns the selection to an in-scope knowledge base when scoping hides it', async () => {
    installFetchMock({ kbItems: [medicareKb, housingKb] })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(
      screen.getByRole('button', { name: 'Show all domains (1 hidden)' }),
    )
    await userEvent.click(await screen.findByRole('button', { name: /housing kb/i }))

    // Warn-only: an explicitly selected out-of-scope KB is honored while shown.
    expect(await screen.findAllByText('Housing KB')).toHaveLength(2)
    expect(screen.getAllByTestId('kb-domain-mismatch').length).toBeGreaterThan(0)

    // Re-scoping drops the out-of-scope selection back to the first in-scope KB.
    await userEvent.click(screen.getByRole('button', { name: 'Scope to active domain' }))
    await waitFor(() => expect(screen.queryByText('Housing KB')).not.toBeInTheDocument())
    expect(screen.getAllByText('Fraud KB')).toHaveLength(2)
  })

  it('shows a warning chip and reasons for documents with ingestion warnings', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    const documentRow = await screen.findByRole('button', {
      name: /existing-policy\.txt/,
    })
    expect(within(documentRow).getByText('2 warnings')).toBeInTheDocument()

    await userEvent.click(documentRow)
    const reasons = await screen.findByTestId('document-warning-reasons')
    expect(within(reasons).getByText(/csv\.ragged_row/)).toBeInTheDocument()
    expect(within(reasons).getByText(/normalization_failed/)).toBeInTheDocument()
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

  it('shows next actions after document submission', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['policy'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Submit documents' }))

    expect(await screen.findByText('1 document accepted.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /watch runs/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /investigate entities/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /review alerts/i })).toBeInTheDocument()
  })

  it('navigates to investigation with the selected knowledge base after document submission', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['policy'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Submit documents' }))

    expect(await screen.findByText('1 document accepted.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /investigate entities/i }))

    expect(routerMocks.navigate).toHaveBeenCalledWith({
      pathname: '/investigation',
      search: 'kb=kb-1',
    })
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
    // File-upload feeds auto-parse on file selection (the manual control is
    // labelled "Re-parse file"); there is no separate "Parse records" step.
    await screen.findByText('Parsed for preview')
    await userEvent.click(screen.getByRole('button', { name: 'Submit records' }))

    // The file-upload feed posts through XMLHttpRequest (for byte-level upload
    // progress), not fetch; a successful receipt in the timeline confirms the
    // multipart upload round-tripped.
    expect(await screen.findByText('1 records accepted for claims_feed.')).toBeInTheDocument()
  })

  it('auto-re-parses when the records file upload draft changes', async () => {
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
    // File-upload feeds auto-parse on selection, enabling submit.
    await screen.findByText('Parsed for preview')
    expect(screen.getByRole('button', { name: 'Submit records' })).toBeEnabled()

    // Changing the file invalidates the prior draft and auto-re-parses the new
    // file, so submit becomes ready again with the updated content.
    await userEvent.upload(
      screen.getByLabelText('Records file'),
      new File(['claim_id,provider_npi,billed_amount\nc2,1234567890,101.25\n'], 'claims-2.csv', {
        type: 'text/csv',
      }),
    )

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Submit records' })).toBeEnabled(),
    )
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

  it('shows unsupported document upload errors in the validation panel', async () => {
    installFetchMock({ documentFail: true })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Submit documents' }))

    expect(await screen.findByText('Backend response')).toBeInTheDocument()
    // Surfaced both in the validation panel and the retryable upload error.
    expect(screen.getAllByText('Unsupported document content type.').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /retry upload/i })).toBeInTheDocument()
  })

  it('retries a failed document upload and succeeds on the second attempt', async () => {
    installFetchMock({ documentFail: true })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Submit documents' }))

    const retry = await screen.findByRole('button', { name: /retry upload/i })

    // Swap the transport to a passing one, then retry the same upload verbatim.
    installFetchMock()
    await userEvent.click(retry)

    expect(await screen.findByText('1 document accepted.')).toBeInTheDocument()
  })

  it('shows structured backend validation arrays for records errors', async () => {
    installFetchMock({ structuredRecordsFail: true })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await parseValidRecords()
    await userEvent.click(screen.getByRole('button', { name: 'Submit records' }))

    expect(await screen.findByText('Backend response')).toBeInTheDocument()
    expect(screen.getByText('body.rows.0.provider_npi: Field required')).toBeInTheDocument()
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

  it('renders the Validate stepper item as idle on cold load (no error chip, no complete chip)', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')

    const validateItem = getStepperItem('Validate')
    expect(within(validateItem).queryByText('Needs attention')).not.toBeInTheDocument()
    expect(within(validateItem).queryByText('Complete')).not.toBeInTheDocument()
  })

  it('flips Validate to Needs attention when an empty document file is queued', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File([''], 'empty.txt', { type: 'text/plain' }),
    )

    const validateItem = getStepperItem('Validate')
    expect(within(validateItem).getByText('Needs attention')).toBeInTheDocument()
  })

  it('marks Validate as Complete when a clean document file is queued', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )

    const validateItem = getStepperItem('Validate')
    expect(within(validateItem).getByText('Complete')).toBeInTheDocument()
  })

  it('keeps Validate idle after Documents source is picked but no files have been uploaded', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))

    const validateItem = getStepperItem('Validate')
    expect(within(validateItem).queryByText('Needs attention')).not.toBeInTheDocument()
    expect(within(validateItem).queryByText('Complete')).not.toBeInTheDocument()
  })
})
