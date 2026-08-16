import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { RecordFeedConfig } from '../../../../api/contracts'
import { apiErrorMessage } from '../../../../lib/apiClient'
import { emptyDraft } from '../../../../stores/ingestionDraftStore'
import type { IngestionDraft } from '../../../../stores/ingestionDraftStore'
import { useRecordsFlow } from '../useRecordsFlow'

const fileUploadFeed: RecordFeedConfig = {
  name: 'claims_feed',
  record_type: 'claim_record',
  source: 'file_upload',
  id_field: 'claim_id',
  record_schema: {},
  entities: [],
  relationships: [],
  observations: [],
}

const pushFeed: RecordFeedConfig = {
  name: 'provider_push',
  record_type: 'provider_record',
  source: 'api_push',
  id_field: 'provider_npi',
  record_schema: {},
  entities: [],
  relationships: [],
  observations: [],
}

const feeds = [fileUploadFeed, pushFeed]

const originalFetch = globalThis.fetch
const originalXhr = globalThis.XMLHttpRequest

/** Minimal XHR stub: rejects the records-file upload with a distinct message. */
function installFailingXhrMock() {
  class FakeUploadXhr {
    url = ''
    status = 0
    response: unknown = { detail: 'file-upload rejected' }
    responseText = ''
    readonly upload: { onprogress: ((event: ProgressEvent) => void) | null } = {
      onprogress: null,
    }
    onload: (() => void) | null = null
    onerror: (() => void) | null = null

    open(_method: string, url: string): void {
      this.url = url
    }

    send(): void {
      this.status = 422
      queueMicrotask(() => this.onload?.())
    }
  }

  globalThis.XMLHttpRequest = FakeUploadXhr as unknown as typeof XMLHttpRequest
}

/** Fails the records push endpoint with a distinct message. */
function installFailingFetchMock() {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.endsWith('/records/kb-1/push')) {
      return new Response(JSON.stringify({ detail: 'push rejected' }), {
        status: 422,
        headers: { 'content-type': 'application/json' },
      })
    }
    return new Response(JSON.stringify({ detail: 'unexpected request' }), {
      status: 404,
      headers: { 'content-type': 'application/json' },
    })
  }) as unknown as typeof fetch
}

function draftFor(patch: Partial<IngestionDraft>): IngestionDraft {
  return { ...emptyDraft(), sourceType: 'records', ...patch }
}

const noopUpload = {
  beginUpload: vi.fn(),
  reportUploadProgress: vi.fn(),
  completeUpload: vi.fn(),
  failUpload: vi.fn(),
}

function renderFlow(initialDraft: IngestionDraft) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }

  return renderHook(
    (draft: IngestionDraft) =>
      useRecordsFlow({
        knowledgeBaseId: 'kb-1',
        draft,
        patchDraft: vi.fn(),
        clearDraft: vi.fn(),
        onSubmitted: vi.fn(),
        feeds,
        upload: noopUpload,
      }),
    { wrapper: Wrapper, initialProps: initialDraft },
  )
}

beforeEach(() => {
  installFailingXhrMock()
  installFailingFetchMock()
})

afterEach(() => {
  globalThis.fetch = originalFetch
  globalThis.XMLHttpRequest = originalXhr
  vi.restoreAllMocks()
})

describe('useRecordsFlow error precedence', () => {
  it('prefers the file-upload mutation error over the push mutation error, pinning the pre-extraction ordering', async () => {
    // Fail the file_upload feed first.
    const { result, rerender } = renderFlow(
      draftFor({
        selectedFeedName: 'claims_feed',
        pendingRecordFile: new File(['claim_id\nc1\n'], 'claims.csv', { type: 'text/csv' }),
        parsedRows: [{ claim_id: 'c1' }],
      }),
    )

    act(() => {
      result.current.submit()
    })

    await waitFor(() => expect(result.current.error).toBeTruthy())
    expect(apiErrorMessage(result.current.error, 'fallback')).toBe('file-upload rejected')

    // Now switch to a non-file-upload feed and fail it too, without the
    // first (file-upload) mutation ever resetting — the reachable scenario
    // the review flagged: two stale errors sitting side by side.
    rerender(
      draftFor({
        selectedFeedName: 'provider_push',
        parsedRows: [{ provider_npi: '1234567890' }],
      }),
    )

    act(() => {
      result.current.submit()
    })

    // Wait for the push mutation to settle without reading `.error` — it is
    // masked by precedence and would never observably change to the push
    // message, which is exactly the property under test.
    await waitFor(() => expect(result.current.runPending).toBe(false))

    // The combined error must still prefer the file-upload mutation's error,
    // matching the pre-extraction page's `uploadRecordFileMutation.error ??
    // pushRecordsMutation.error` precedence — even though the push mutation
    // is the one that failed most recently.
    expect(apiErrorMessage(result.current.error, 'fallback')).toBe('file-upload rejected')
  })
})
