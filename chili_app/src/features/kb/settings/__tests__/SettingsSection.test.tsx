import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { KnowledgeBaseSummaryResponse } from '../../../../api/contracts'
import { useIngestionDraftStore } from '../../../../stores/ingestionDraftStore'
import { SettingsSection } from '../SettingsSection'

const knowledgeBase: KnowledgeBaseSummaryResponse = {
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

function renderSection(onDeleted = vi.fn()) {
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
    <SettingsSection knowledgeBase={knowledgeBase} onDeleted={onDeleted} />,
    { wrapper: Wrapper },
  )
  return { ...result, onDeleted }
}

const originalFetch = globalThis.fetch

beforeEach(() => {
  useIngestionDraftStore.getState().reset()
  globalThis.fetch = vi.fn(async () => new Response(null, { status: 204 })) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

describe('SettingsSection', () => {
  it('states the blast radius and refuses to delete until the name is typed', async () => {
    renderSection()

    await userEvent.click(screen.getByRole('button', { name: 'Delete knowledge base' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('8 documents')
    expect(dialog).toHaveTextContent('53 entities')
    expect(dialog).toHaveTextContent('cannot be undone')

    const confirm = within(dialog).getByRole('button', { name: 'Delete knowledge base' })
    expect(confirm).toBeDisabled()

    await userEvent.type(within(dialog).getByRole('textbox'), 'Fraud KB')
    expect(confirm).toBeEnabled()
  })

  it('drops the deleted knowledge base’s draft — it has nowhere to submit to', async () => {
    useIngestionDraftStore.getState().updateDraft('kb-1', {
      pendingFiles: [new File(['x'], 'a.txt', { type: 'text/plain' })],
    })
    const { onDeleted } = renderSection()

    await userEvent.click(screen.getByRole('button', { name: 'Delete knowledge base' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByRole('textbox'), 'Fraud KB')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete knowledge base' }))

    await waitFor(() => {
      expect(useIngestionDraftStore.getState().draftsByKb['kb-1']).toBeUndefined()
      expect(onDeleted).toHaveBeenCalled()
    })
  })

  it('shows the identity details as copyable text rather than in the main flow', () => {
    renderSection()

    expect(screen.getByText('kb-1')).toBeInTheDocument()
    expect(screen.getByText('medicare_fraud')).toBeInTheDocument()
  })
})
