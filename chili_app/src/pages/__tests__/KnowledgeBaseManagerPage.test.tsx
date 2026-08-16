import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useIngestionDraftStore } from '../../stores/ingestionDraftStore'
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
  status: 'queued' | 'running' | 'completed' | 'failed' | 'canceled' | 'replayed'
  total_entities: number
  updated_at: string
}

type MockWorkflow = {
  id: string
  knowledge_base_id: string
  workflow_type: 'ingestion' | 'graph_build' | 'analytics' | 'monitoring'
  status: 'queued' | 'running' | 'awaiting_approval' | 'completed' | 'failed' | 'cancelled'
  current_step: string
  started_at: string
  updated_at: string
}

type MockDocumentSummary = {
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
  drop_sample_reasons?: string[]
  created_at: string
  warning_count: number
  warning_reasons: string[]
}

const existingDocument: MockDocumentSummary = {
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
  previewFail = false,
  previewText = 'Section 1\nSection 2\nSection 3',
  previewTextByDocument = {},
  previewDelayMs = 0,
  kbDomain = null,
  kbItems,
  documentItems,
  emptyInventory = false,
  scoreRunItems = [],
  workflowItems = [],
}: {
  documentFail?: boolean
  recordsFail?: boolean
  structuredRecordsFail?: boolean
  previewFail?: boolean
  previewText?: string
  previewTextByDocument?: Record<string, string>
  previewDelayMs?: number
  /** `domain` stamped on the mocked knowledge base (null = legacy/unknown). */
  kbDomain?: string | null
  /** Full KB list override; defaults to the single kb-1 stamped with `kbDomain`. */
  kbItems?: MockKnowledgeBase[]
  /** Full document inventory override for kb-1. */
  documentItems?: MockDocumentSummary[]
  /** kb-1 has landed nothing yet — the brand-new knowledge base case. */
  emptyInventory?: boolean
  scoreRunItems?: MockScoreRun[]
  workflowItems?: MockWorkflow[]
} = {}) {
  const knowledgeBaseItems = (kbItems ?? [{ ...medicareKb, domain: kbDomain }]).map((item) => (
    emptyInventory && item.id === 'kb-1'
      ? { ...item, document_count: 0, entity_count: 0, relationship_count: 0 }
      : item
  ))
  const inventoryItems = emptyInventory ? [] : documentItems ?? [existingDocument]
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
      return new Response(JSON.stringify({ items: workflowItems }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }

    if (url.includes('/knowledgebases/kb-1/score-runs') && init?.method === 'POST') {
      const body = typeof init.body === 'string' ? JSON.parse(init.body) as Record<string, unknown> : {}
      const run = {
        catalog_version: String(body.catalog_version ?? 'cms-fraud-features-v1'),
        created_at: '2026-08-02T10:00:00Z',
        error_summary: null,
        failed_entities: 0,
        finished_at: null,
        id: 'score-run-started',
        idempotency_key: null,
        knowledge_base_id: 'kb-1',
        model_version: String(body.model_version ?? 'risk-linear-v1'),
        replay_of_run_id: null,
        requested_by: null,
        scored_entities: 0,
        started_at: null,
        status: 'queued',
        total_entities: 2,
        updated_at: '2026-08-02T10:00:00Z',
      }
      return new Response(JSON.stringify({ run, batches: [], created: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }

    const scoreRunDetailMatch = url.match(/\/knowledgebases\/kb-1\/score-runs\/([^/?]+)$/)
    if (scoreRunDetailMatch) {
      const run = scoreRunItems.find((item) => item.id === scoreRunDetailMatch[1])
        ?? (scoreRunDetailMatch[1] === 'score-run-started'
          ? {
              catalog_version: 'cms-fraud-features-v1',
              created_at: '2026-08-02T10:00:00Z',
              error_summary: null,
              failed_entities: 0,
              finished_at: null,
              id: 'score-run-started',
              idempotency_key: null,
              knowledge_base_id: 'kb-1',
              model_version: 'risk-linear-v1',
              replay_of_run_id: null,
              requested_by: null,
              scored_entities: 0,
              started_at: null,
              status: 'queued',
              total_entities: 2,
              updated_at: '2026-08-02T10:00:00Z',
            } satisfies MockScoreRun
          : null)
      if (run) {
        return new Response(JSON.stringify({ run, batches: [], created: false }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      }
    }

    if (url.includes('/knowledgebases/kb-1/score-runs')) {
      return new Response(
        JSON.stringify({
          items: scoreRunItems,
          total: scoreRunItems.length,
          limit: 1,
          offset: 0,
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
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
      if (emptyInventory) {
        return new Response(JSON.stringify({ items: [], total: 0 }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      }

      return new Response(
        JSON.stringify({
          items: inventoryItems,
          total: inventoryItems.length,
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    }

    const previewMatch = url.match(/\/knowledgebases\/kb-1\/documents\/([^/]+)\/preview$/)
    if (previewMatch) {
      if (previewDelayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, previewDelayMs))
      }
      if (previewFail) {
        return new Response(JSON.stringify({ detail: 'Preview failed' }), {
          status: 415,
          headers: { 'content-type': 'application/json' },
        })
      }
      const documentId = decodeURIComponent(previewMatch[1])
      const document = inventoryItems.find((item) => item.id === documentId)
      if (!document) {
        return new Response(JSON.stringify({ detail: 'Document not found' }), {
          status: 404,
          headers: { 'content-type': 'application/json' },
        })
      }
      const selectedPreviewText = previewTextByDocument[documentId] ?? previewText

      return new Response(
        JSON.stringify({
          knowledge_base_id: 'kb-1',
          document_id: documentId,
          filename: document.filename,
          content_type: 'text/plain',
          preview_text: selectedPreviewText,
          line_count: selectedPreviewText.length === 0 ? 0 : selectedPreviewText.split('\n').length,
          truncated: false,
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

    if (init?.method === 'DELETE') {
      return new Response(null, { status: 204 })
    }

    return new Response('{}', {
      status: 404,
      headers: { 'content-type': 'application/json' },
    })
  }) as unknown as typeof fetch
}

/** URLs of every DELETE the page has issued — destructive actions must not fire unconfirmed. */
function deleteRequests(): string[] {
  const mock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
  return mock.mock.calls
    .filter((call) => (call[1] as RequestInit | undefined)?.method === 'DELETE')
    .map((call) => String(call[0]))
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

describe('KnowledgeBaseManagerPage ingestion', () => {
  const originalFetch = globalThis.fetch
  const originalXhr = globalThis.XMLHttpRequest

  beforeEach(() => {
    useIngestionDraftStore.getState().reset()
    routerMocks.navigate.mockReset()
    installFetchMock()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    globalThis.XMLHttpRequest = originalXhr
    vi.restoreAllMocks()
  })

  it('calls the destination what the sidebar calls it', async () => {
    // The page used to answer to three names at once — "Knowledge Bases" in the
    // nav, "Ingestion Studio" as the title, "Ingestion Control" as the eyebrow.
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' }),
    ).toBeInTheDocument()
    expect(screen.queryByText(/ingestion studio/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/ingestion control/i)).not.toBeInTheDocument()
  })

  it('renders the ingestion shell and existing knowledge base', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })).toBeInTheDocument()
    // The staging headings moved into AddDataSection's own copy when the
    // add-data flow was extracted (Task 5): the page renders through it now,
    // so this checks the same DOM the section owns, not the old page text.
    expect(screen.getByText('Choose a source')).toBeInTheDocument()
    expect(screen.getByText('Review and submit')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeInTheDocument()
    expect(await screen.findAllByText('Fraud KB')).toHaveLength(2)
    expect(screen.getByText('existing-policy.txt')).toBeInTheDocument()
  })

  it('warns without blocking when the knowledge base was created under another domain', async () => {
    // Active domain in the mocked config is medicare_fraud.
    installFetchMock({ kbDomain: 'food_supply_chain' })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })

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

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await screen.findAllByText('Fraud KB')

    expect(screen.queryByTestId('kb-domain-mismatch')).not.toBeInTheDocument()
    expect(screen.queryByTestId('kb-domain-mismatch-note')).not.toBeInTheDocument()
    expect(screen.queryByTestId('kb-domain-unknown')).not.toBeInTheDocument()
  })

  it('renders a tolerated unknown state for a legacy knowledge base without a domain', async () => {
    // Default mock leaves kbDomain null (legacy KB created before stamping).
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await screen.findAllByText('Fraud KB')

    // List entry + summary card each show the subtle unknown chip, no warning.
    expect(screen.getAllByTestId('kb-domain-unknown')).toHaveLength(2)
    expect(screen.queryByTestId('kb-domain-mismatch')).not.toBeInTheDocument()
    expect(screen.queryByTestId('kb-domain-mismatch-note')).not.toBeInTheDocument()
  })

  it('hides knowledge bases from other domains by default and reveals them with the toggle', async () => {
    installFetchMock({ kbItems: [medicareKb, housingKb] })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
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

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
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

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })

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

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })

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

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    expect(await screen.findAllByText('Fraud KB')).toHaveLength(2)
  })

  it('returns the selection to an in-scope knowledge base when scoping hides it', async () => {
    installFetchMock({ kbItems: [medicareKb, housingKb] })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
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

  it('shows a warning chip and reasons behind an explicit toggle', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    const documentRow = await screen.findByRole('button', {
      name: /existing-policy\.txt/,
    })
    expect(within(documentRow).getByText('2 warnings')).toBeInTheDocument()

    // Reasons used to be reachable only by hover (a `title`) or by selecting
    // the row. Neither is discoverable, and neither works on touch.
    await userEvent.click(screen.getByRole('button', { name: 'Show 2 warnings' }))
    const reasons = await screen.findByTestId('document-warning-reasons')
    expect(within(reasons).getByText(/csv\.ragged_row/)).toBeInTheDocument()
    expect(within(reasons).getByText(/normalization_failed/)).toBeInTheDocument()
  })

  it('renders the durable lifecycle state, not the registration status', async () => {
    installFetchMock({
      documentItems: [
        {
          ...existingDocument,
          id: 'doc-empty',
          filename: 'resume-like.txt',
          status: 'ready',
          current_status: 'extracted_empty',
          warning_count: 0,
          warning_reasons: [],
        },
      ],
    })
    renderWithClient(<KnowledgeBaseManagerPage />)

    // A document that produced no entities used to read as a green "ready".
    const row = await screen.findByRole('button', { name: /resume-like\.txt/ })
    expect(within(row).getByText('No entities')).toBeInTheDocument()
    expect(within(row).queryByText('Validated')).not.toBeInTheDocument()
  })

  it('shows the failure reason on a failed document without any clicks', async () => {
    installFetchMock({
      documentItems: [
        {
          ...existingDocument,
          id: 'doc-failed',
          filename: 'broken.json',
          status: 'ready',
          current_status: 'failed',
          last_error: 'Parser gave up: unexpected token at line 3',
          warning_count: 0,
          warning_reasons: [],
        },
      ],
    })
    renderWithClient(<KnowledgeBaseManagerPage />)

    const row = await screen.findByRole('button', { name: /broken\.json/ })
    expect(within(row).getByText('Failed')).toBeInTheDocument()
    expect(within(row).getByText(/Parser gave up/)).toBeInTheDocument()
  })

  it('reports dropped entities and relationships as exact counts', async () => {
    installFetchMock({
      documentItems: [
        {
          ...existingDocument,
          id: 'doc-drops',
          filename: 'partial.json',
          current_status: 'validated',
          dropped_entity_count: 3,
          dropped_relationship_count: 2,
          warning_count: 0,
          warning_reasons: [],
        },
      ],
    })
    renderWithClient(<KnowledgeBaseManagerPage />)

    const row = await screen.findByRole('button', { name: /partial\.json/ })
    expect(within(row).getByText(/3 entities dropped/)).toBeInTheDocument()
    expect(within(row).getByText(/2 relationships dropped/)).toBeInTheDocument()
  })

  it('asks the API for a filtered inventory when a lifecycle filter is chosen', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('existing-policy.txt')
    await userEvent.selectOptions(
      screen.getByLabelText('Filter documents by status'),
      'extracted_empty',
    )

    await waitFor(() => {
      const requested = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls
        .map((call) => String(call[0]))
        .filter((url) => url.includes('/documents?'))
      expect(requested.some((url) => url.includes('status=extracted_empty'))).toBe(true)
    })
  })

  it('states an empty knowledge base once, with an action (UXA-305)', async () => {
    // A brand-new KB used to stack three cards that all said the same thing:
    // "No runs yet", "No documents yet", "No document selected".
    installFetchMock({ emptyInventory: true })
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByText('No documents yet')).toBeInTheDocument()
    expect(screen.queryByText('No runs yet')).not.toBeInTheDocument()
    expect(screen.queryByText('No document selected')).not.toBeInTheDocument()
    expect(screen.queryByText('Document preview')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Stage a source' })).toBeInTheDocument()
  })

  it('sends the empty-inventory action back to the staging step (UXA-305)', async () => {
    // Stages are on one page for now (routing lands in a later task): the
    // empty-inventory action's only observable effect is scrolling the
    // staging section into view. jsdom does not implement scrollIntoView, so
    // the component guards the call — stub it in to observe the guard passing.
    const scrollIntoView = vi.fn()
    HTMLElement.prototype.scrollIntoView = scrollIntoView
    installFetchMock({ emptyInventory: true })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await userEvent.click(await screen.findByRole('button', { name: 'Stage a source' }))

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })

    delete (HTMLElement.prototype as { scrollIntoView?: () => void }).scrollIntoView
  })

  it('hides the run timeline card when a knowledge base has documents but no workflows (UXA-305)', async () => {
    // Documents are the data section's business now; a knowledge base can
    // have documents with no run submitted in this session. The timeline no
    // longer earns a card just because documents exist — showing its own
    // "No runs yet" here would be a second card saying nothing happened yet,
    // when the data section already covers what has landed.
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByText('existing-policy.txt')).toBeInTheDocument()
    expect(screen.queryByText('No runs yet')).not.toBeInTheDocument()
    expect(screen.queryByText('Run timeline')).not.toBeInTheDocument()
    expect(screen.getByText('Document preview')).toBeInTheDocument()
  })

  it('shows the run timeline once a workflow exists, independent of documents (UXA-305)', async () => {
    installFetchMock({
      workflowItems: [
        {
          id: 'workflow-1',
          knowledge_base_id: 'kb-1',
          workflow_type: 'ingestion',
          status: 'queued',
          current_step: 'validate',
          started_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-01T00:00:00Z',
        },
      ],
    })
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByText('Run timeline')).toBeInTheDocument()
    expect(screen.queryByText('No runs yet')).not.toBeInTheDocument()
  })

  it('starts score-all without requiring client-side entity ids', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('existing-policy.txt')
    await userEvent.click(screen.getByRole('button', { name: 'Start score-all' }))

    await screen.findByText('score-run-started')
    const startCall = vi
      .mocked(globalThis.fetch)
      .mock.calls.find((call) => {
        const url = String(call[0])
        const init = call[1]
        return url.endsWith('/knowledgebases/kb-1/score-runs') && init?.method === 'POST'
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

  it('hydrates the score-run panel from the latest durable run', async () => {
    installFetchMock({
      scoreRunItems: [
        {
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
        },
      ],
    })
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByText('score-run-latest')).toBeInTheDocument()
    expect(screen.getByText('2 / 4')).toBeInTheDocument()
  })

  it('renders document preview content for the selected inventory document', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByText('Document preview')).toBeInTheDocument()
    expect(await screen.findByText(/Section 1/)).toBeInTheDocument()
    expect(screen.getByText(/3 lines from existing-policy\.txt/)).toBeInTheDocument()
  })

  it('honors a ?document= deep-link for document preview selection', async () => {
    installFetchMock({
      documentItems: [
        existingDocument,
        {
          ...existingDocument,
          id: 'doc-selected',
          filename: 'selected-claim.txt',
          warning_count: 0,
          warning_reasons: [],
        },
      ],
      previewTextByDocument: {
        'doc-selected': 'Selected claim chunk\nLine two',
      },
    })

    renderWithClient(
      <KnowledgeBaseManagerPage />,
      ['/knowledge-bases?kb=kb-1&document=doc-selected&chunk=7'],
    )

    expect(await screen.findByText(/Selected claim chunk/)).toBeInTheDocument()
    expect(screen.getByText(/2 lines from selected-claim\.txt/)).toBeInTheDocument()

    const requestedUrls = vi
      .mocked(globalThis.fetch)
      .mock.calls.map((call) => String(call[0]))
    expect(
      requestedUrls.some((requestedUrl) =>
        requestedUrl.endsWith('/knowledgebases/kb-1/documents/doc-selected/preview'),
      ),
    ).toBe(true)
    expect(
      requestedUrls.some((requestedUrl) =>
        requestedUrl.endsWith('/knowledgebases/kb-1/documents/doc-existing/preview'),
      ),
    ).toBe(false)
  })

  it('renders document preview empty state when preview text is blank', async () => {
    installFetchMock({ previewText: '' })
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByText('No preview text returned')).toBeInTheDocument()
  })

  it('renders document preview error state when the preview API fails', async () => {
    installFetchMock({ previewFail: true })
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByText('Document preview could not be loaded from the API.')).toBeInTheDocument()
  })

  it('renders document preview loading state while preview data is in flight', async () => {
    installFetchMock({ previewDelayMs: 25 })
    renderWithClient(<KnowledgeBaseManagerPage />)

    expect(await screen.findByText('Loading document preview')).toBeInTheDocument()
    expect(await screen.findByText(/Section 1/)).toBeInTheDocument()
  })

  it('clears the staged draft once a document submission is accepted', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    expect(await screen.findByText('Submission accepted. Watch for queued or running workflow updates.')).toBeInTheDocument()
    // The draft belonged to an in-flight submission that the server now owns.
    expect(screen.queryByText('policy.txt')).not.toBeInTheDocument()
  })

  it('shows next actions after document submission', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['policy'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    expect(await screen.findByText('Submission accepted. Watch for queued or running workflow updates.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /investigate entities/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /review alerts/i })).toBeInTheDocument()
  })

  it('navigates to investigation with the selected knowledge base after document submission', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['policy'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    expect(await screen.findByText('Submission accepted. Watch for queued or running workflow updates.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /investigate entities/i }))

    expect(routerMocks.navigate).toHaveBeenCalledWith({
      pathname: '/investigation',
      search: 'kb=kb-1',
    })
  })

  it('parses and submits records through a configured feed', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await parseValidRecords()
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    expect(await screen.findByText('Submission accepted. Watch for queued or running workflow updates.')).toBeInTheDocument()
  })

  it('uploads configured file-upload records feeds through the records file endpoint', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
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
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    // The file-upload feed posts through XMLHttpRequest (for byte-level upload
    // progress), not fetch; the accepted handoff confirms the multipart
    // upload round-tripped.
    expect(await screen.findByText('Submission accepted. Watch for queued or running workflow updates.')).toBeInTheDocument()
  })

  it('auto-re-parses when the records file upload draft changes', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
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
    expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeEnabled()

    // Changing the file invalidates the prior draft and auto-re-parses the new
    // file, so submit becomes ready again with the updated content.
    await userEvent.upload(
      screen.getByLabelText('Records file'),
      new File(['claim_id,provider_npi,billed_amount\nc2,1234567890,101.25\n'], 'claims-2.csv', {
        type: 'text/csv',
      }),
    )

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeEnabled(),
    )
  })

  it('requires re-parsing after editing pasted api-push records', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await parseValidRecords()
    expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeEnabled()

    await userEvent.type(screen.getByLabelText('Records content'), '1')

    expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeDisabled()
  })

  it('shows client validation before records submit', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await userEvent.click(screen.getByRole('radio', { name: /Structured Records/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    expect(await screen.findByText('Select a structured records feed before submitting.')).toBeInTheDocument()
  })

  it('shows backend records errors in the validation panel', async () => {
    installFetchMock({ recordsFail: true })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await parseValidRecords()
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    expect(await screen.findByText('Checked after upload')).toBeInTheDocument()
    expect(screen.getByText('Records backend rejected the file.')).toBeInTheDocument()
  })

  it('shows unsupported document upload errors in the validation panel', async () => {
    installFetchMock({ documentFail: true })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    expect(await screen.findByText('Checked after upload')).toBeInTheDocument()
    // Surfaced both in the validation panel and the retryable upload error.
    expect(screen.getAllByText('Unsupported document content type.').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /retry upload/i })).toBeInTheDocument()
  })

  it('retries a failed document upload and succeeds on the second attempt', async () => {
    installFetchMock({ documentFail: true })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    const retry = await screen.findByRole('button', { name: /retry upload/i })

    // Swap the transport to a passing one, then retry the same upload verbatim.
    installFetchMock()
    await userEvent.click(retry)

    expect(await screen.findByText('Submission accepted. Watch for queued or running workflow updates.')).toBeInTheDocument()
  })

  it('shows structured backend validation arrays for records errors', async () => {
    installFetchMock({ structuredRecordsFail: true })
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await parseValidRecords()
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    expect(await screen.findByText('Checked after upload')).toBeInTheDocument()
    expect(screen.getByText('body.rows.0.provider_npi: Field required')).toBeInTheDocument()
  })

  it('keeps the accepted-submission state when a later records submit fails validation', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))
    await screen.findByText('Submission accepted. Watch for queued or running workflow updates.')

    await userEvent.click(screen.getByRole('radio', { name: /Structured Records/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    await waitFor(() => {
      expect(screen.getByText('Submission accepted. Watch for queued or running workflow updates.')).toBeInTheDocument()
      expect(screen.getByText('Select a structured records feed before submitting.')).toBeInTheDocument()
    })
  })

  it('gates knowledge base deletion behind a typed-name confirmation', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByRole('heading', { level: 1, name: 'Knowledge Bases' })
    await userEvent.click(screen.getByRole('button', { name: 'Delete selected knowledge base' }))

    const dialog = screen.getByRole('dialog')
    // The blast radius is stated in counts, not "this action cannot be undone".
    expect(dialog).toHaveTextContent('2 entities')
    expect(dialog).toHaveTextContent('1 relationship')

    const confirm = within(dialog).getByRole('button', { name: 'Delete knowledge base' })
    expect(confirm).toBeDisabled()
    expect(deleteRequests()).toHaveLength(0)

    await userEvent.type(within(dialog).getByRole('textbox'), 'Fraud KB')
    expect(confirm).toBeEnabled()
    await userEvent.click(confirm)

    await waitFor(() => expect(deleteRequests()).toHaveLength(1))
    expect(deleteRequests()[0]).toContain('/knowledgebases/kb-1')
  })

  it('lets a cancelled document removal leave the document in place', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    // The data section fetches its own document inventory now, independent of
    // the page-level loading gate — wait for it to land before interacting.
    await screen.findByText('existing-policy.txt')
    await userEvent.click(screen.getByRole('button', { name: 'Remove document' }))

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('existing-policy.txt')

    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(deleteRequests()).toHaveLength(0)
    expect(screen.getByText('existing-policy.txt')).toBeInTheDocument()
  })
})
