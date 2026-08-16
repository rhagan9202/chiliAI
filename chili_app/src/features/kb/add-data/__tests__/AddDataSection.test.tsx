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

/** Transport outcomes, flipped per test (and mid-test, for the retry case). */
let documentFail = false
let recordsFileFail = false
let recordsPushFail = false
let recordsPushStructuredFail = false

const originalFetch = globalThis.fetch
const originalXhr = globalThis.XMLHttpRequest

/**
 * Minimal XMLHttpRequest stub. Documents and records *files* are uploaded
 * through XHR so byte-level progress can be reported; this stub answers those
 * with the same canned bodies the fetch mock returns for the other routes.
 */
function installXhrMock() {
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

function outcomeFor(url: string): { status: number; body: unknown } {
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
    if (recordsFileFail) {
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

/** Stages a valid pasted api-push records batch and parses it. */
async function parseValidRecords() {
  await userEvent.click(screen.getByRole('radio', { name: /Structured Records/i }))
  await userEvent.selectOptions(screen.getByLabelText('Records feed'), 'provider_push')
  await userEvent.selectOptions(screen.getByLabelText('Records format'), 'CSV')
  await userEvent.type(screen.getByLabelText('Records content'), 'provider_npi\n1234567890\n')
  await userEvent.click(screen.getByRole('button', { name: 'Parse records' }))
}

beforeEach(() => {
  useIngestionDraftStore.getState().reset()
  documentFail = false
  recordsFileFail = false
  recordsPushFail = false
  recordsPushStructuredFail = false
  installXhrMock()

  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()

    if (url.endsWith('/config/domain')) {
      return new Response(JSON.stringify(domainConfig), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }

    if (url.endsWith('/records/kb-1/push')) {
      if (recordsPushStructuredFail) {
        return new Response(
          JSON.stringify({
            detail: [{ loc: ['body', 'rows', 0, 'provider_npi'], msg: 'Field required' }],
          }),
          { status: 422, headers: { 'content-type': 'application/json' } },
        )
      }
      if (recordsPushFail) {
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

    throw new Error(`unexpected request: ${url}`)
  }) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  globalThis.XMLHttpRequest = originalXhr
  vi.restoreAllMocks()
})

describe('AddDataSection', () => {
  it('will not submit with nothing staged, and says what is missing', async () => {
    renderSection()

    const submit = await screen.findByRole('button', { name: 'Run ingestion' })
    expect(submit).toBeDisabled()
    expect(screen.getByText('Select source type')).toBeInTheDocument()
  })

  // Rehomed from KnowledgeBaseManagerPage.test.tsx: the staging flow reads as
  // two steps and one primary action, wherever it is mounted.
  it('lays the staging flow out as choose a source, then review and submit', async () => {
    renderSection()

    expect(await screen.findByText('Choose a source')).toBeInTheDocument()
    expect(screen.getByText('Review and submit')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeInTheDocument()
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

  // Rehomed from KnowledgeBaseManagerPage.test.tsx: the submission is the
  // server's business once accepted, so nothing about it stays in this tab's
  // draft — the staged file disappearing is what is observable.
  it('clears the staged draft and reports the submission once documents are accepted', async () => {
    const { onSubmitted } = renderSection()

    await userEvent.click(await screen.findByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files', { exact: true }),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    await waitFor(() => expect(screen.queryByText('policy.txt')).not.toBeInTheDocument())
    expect(onSubmitted).toHaveBeenCalled()
  })

  // Rehomed.
  it('parses and submits records through a configured api-push feed', async () => {
    const { onSubmitted } = renderSection()

    await screen.findByRole('button', { name: 'Run ingestion' })
    await parseValidRecords()
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    // A successful submit clears the whole draft, including the source-type
    // choice, so the records panel (and its now-submitted content) unmounts.
    await waitFor(() => expect(screen.queryByLabelText('Records content')).not.toBeInTheDocument())
    expect(onSubmitted).toHaveBeenCalled()
  })

  // Rehomed: file-upload feeds post through XMLHttpRequest (for byte-level
  // upload progress), not fetch; the draft clearing confirms the multipart
  // upload round-tripped.
  it('uploads configured file-upload records feeds through the records file endpoint', async () => {
    renderSection()

    await userEvent.click(await screen.findByRole('radio', { name: /Structured Records/i }))
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

    await waitFor(() => expect(screen.queryByLabelText('Records file')).not.toBeInTheDocument())
  })

  // Rehomed.
  it('auto-re-parses when the records file upload draft changes', async () => {
    renderSection()

    await userEvent.click(await screen.findByRole('radio', { name: /Structured Records/i }))
    await userEvent.selectOptions(screen.getByLabelText('Records feed'), 'claims_feed')
    await userEvent.upload(
      screen.getByLabelText('Records file'),
      new File(['claim_id,provider_npi,billed_amount\nc1,1234567890,99.50\n'], 'claims.csv', {
        type: 'text/csv',
      }),
    )
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

    await waitFor(() => expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeEnabled())
  })

  // Rehomed: an edit after parsing means the preview no longer describes what
  // would be submitted, so submit waits for a re-parse.
  it('requires re-parsing after editing pasted api-push records', async () => {
    renderSection()

    await screen.findByRole('button', { name: 'Run ingestion' })
    await parseValidRecords()
    expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeEnabled()

    await userEvent.type(screen.getByLabelText('Records content'), '1')

    expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeDisabled()
  })

  // Rehomed.
  it('shows client validation before records submit', async () => {
    renderSection()

    await userEvent.click(await screen.findByRole('radio', { name: /Structured Records/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    expect(
      await screen.findByText('Select a structured records feed before submitting.'),
    ).toBeInTheDocument()
  })

  // Rehomed.
  it('shows backend records errors in the validation panel', async () => {
    recordsPushFail = true
    renderSection()

    await screen.findByRole('button', { name: 'Run ingestion' })
    await parseValidRecords()
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    expect(await screen.findByText('Checked after upload')).toBeInTheDocument()
    expect(screen.getByText('Records backend rejected the file.')).toBeInTheDocument()
  })

  // Rehomed: a FastAPI validation array is a list of field errors, not a
  // string, and it has to read as one.
  it('shows structured backend validation arrays for records errors', async () => {
    recordsPushStructuredFail = true
    renderSection()

    await screen.findByRole('button', { name: 'Run ingestion' })
    await parseValidRecords()
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    expect(await screen.findByText('Checked after upload')).toBeInTheDocument()
    expect(screen.getByText('body.rows.0.provider_npi: Field required')).toBeInTheDocument()
  })

  // Rehomed.
  it('shows unsupported document upload errors in the validation panel', async () => {
    documentFail = true
    renderSection()

    await userEvent.click(await screen.findByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files', { exact: true }),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    expect(await screen.findByText('Checked after upload')).toBeInTheDocument()
    // Surfaced both in the validation panel and the retryable upload error.
    expect(screen.getAllByText('Unsupported document content type.').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /retry upload/i })).toBeInTheDocument()
  })

  // Rehomed: the retry re-runs the same upload verbatim, so a transport that
  // has come back works without re-staging anything.
  it('retries a failed document upload and succeeds on the second attempt', async () => {
    documentFail = true
    renderSection()

    await userEvent.click(await screen.findByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files', { exact: true }),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))

    const retry = await screen.findByRole('button', { name: /retry upload/i })

    documentFail = false
    await userEvent.click(retry)

    await waitFor(() => expect(screen.queryByText('policy.txt')).not.toBeInTheDocument())
  })
})
