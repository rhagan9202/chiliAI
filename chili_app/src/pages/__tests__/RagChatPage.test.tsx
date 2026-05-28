import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RagChatPage } from '../RagChatPage'

const mocks = vi.hoisted(() => ({
  knowledgeBases: [] as Array<{
    id: string
    name: string
    description: string
    status: string
    document_count: number
    entity_count: number
    relationship_count: number
    created_at: string
  }>,
  navigate: vi.fn(),
  setSearchParams: vi.fn(),
  searchParams: new URLSearchParams(),
  createConversation: vi.fn(),
  addMessage: vi.fn(),
  conversation: null as null | {
    id: string
    title: string
    knowledge_base_id: string
    messages: Array<{
      id: string
      role: 'user' | 'assistant'
      content: string
      created_at: string
      citation_ids: string[]
      citations: Array<{
        record_id: string
        content_id: string
        score: number
        snippet: string
        document_id?: string | null
        chunk_index?: number | null
        highlight?: string | null
        entity_id?: string | null
      }>
    }>
  },
}))

vi.mock('react-router-dom', () => ({
  useNavigate: () => mocks.navigate,
  useSearchParams: () => [mocks.searchParams, mocks.setSearchParams],
}))

vi.mock('../../api/knowledgebases', () => ({
  useKnowledgeBases: () => ({
    isLoading: false,
    isError: false,
    data: { items: mocks.knowledgeBases, total: mocks.knowledgeBases.length },
  }),
}))

vi.mock('../../api/rag', () => ({
  useConversation: () => ({
    isLoading: false,
    isError: false,
    data: mocks.conversation ?? undefined,
  }),
  useCreateConversation: () => ({
    isPending: false,
    mutate: mocks.createConversation,
  }),
  useAddMessage: () => ({
    isPending: false,
    mutate: mocks.addMessage,
  }),
}))

const KB_ONE = {
  id: 'kb-1',
  name: 'Fraud KB',
  description: '',
  status: 'ready',
  document_count: 1,
  entity_count: 2,
  relationship_count: 1,
  created_at: '2026-05-10T00:00:00Z',
}

const KB_TWO = {
  id: 'kb-2',
  name: 'Policy KB',
  description: '',
  status: 'building',
  document_count: 0,
  entity_count: 0,
  relationship_count: 0,
  created_at: '2026-05-11T00:00:00Z',
}

describe('RagChatPage', () => {
  beforeEach(() => {
    mocks.knowledgeBases = []
    mocks.navigate.mockReset()
    mocks.setSearchParams.mockReset()
    mocks.searchParams = new URLSearchParams()
    mocks.createConversation.mockReset()
    mocks.addMessage.mockReset()
    mocks.conversation = null
  })

  it('renders a Create Knowledge Base CTA when no KBs exist and navigates on click', async () => {
    render(<RagChatPage />)

    expect(screen.getByText('No knowledge base available')).toBeInTheDocument()

    const cta = screen.getByRole('button', { name: /create knowledge base/i })
    await userEvent.click(cta)

    expect(mocks.navigate).toHaveBeenCalledWith('/knowledge-bases')
  })

  it('renders an option for each KB and defaults to the first one', () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]

    render(<RagChatPage />)

    const select = screen.getByLabelText('Knowledge base') as HTMLSelectElement
    expect(select.value).toBe('kb-1')
    expect(screen.getByRole('option', { name: /Fraud KB · ready/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Policy KB · building/ })).toBeInTheDocument()
  })

  it('honors the ?kb=... URL parameter when it matches an existing KB', () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]
    mocks.searchParams = new URLSearchParams('kb=kb-2')

    render(<RagChatPage />)

    const select = screen.getByLabelText('Knowledge base') as HTMLSelectElement
    expect(select.value).toBe('kb-2')
  })

  it('falls back to the first KB when ?kb=... is unknown', () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]
    mocks.searchParams = new URLSearchParams('kb=missing')

    render(<RagChatPage />)

    const select = screen.getByLabelText('Knowledge base') as HTMLSelectElement
    expect(select.value).toBe('kb-1')
  })

  it('updates the URL params when the user picks a different KB', async () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]

    render(<RagChatPage />)

    await userEvent.selectOptions(screen.getByLabelText('Knowledge base'), 'kb-2')

    expect(mocks.setSearchParams).toHaveBeenCalledTimes(1)
    const arg = mocks.setSearchParams.mock.calls[0][0] as URLSearchParams
    expect(arg.get('kb')).toBe('kb-2')
  })

  it('clears any in-progress draft when the user switches KB', async () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]

    render(<RagChatPage />)

    const textarea = screen.getByPlaceholderText(
      'Ask the investigation assistant about an entity, alert, or evidence trail',
    )
    await userEvent.type(textarea, 'partial question')
    expect((textarea as HTMLTextAreaElement).value).toBe('partial question')

    await userEvent.selectOptions(screen.getByLabelText('Knowledge base'), 'kb-2')

    expect((textarea as HTMLTextAreaElement).value).toBe('')
  })

  it('renders rich assistant citations when the backend provides provenance', () => {
    mocks.knowledgeBases = [KB_ONE]
    mocks.conversation = {
      id: 'conversation-1',
      title: 'Investigation thread',
      knowledge_base_id: 'kb-1',
      messages: [
        {
          id: 'message-1',
          role: 'assistant',
          content: 'Claim pattern is anomalous.',
          created_at: '2026-05-12T00:00:00Z',
          citation_ids: ['chunk-17'],
          citations: [
            {
              record_id: 'record-1',
              content_id: 'chunk-17',
              score: 0.91,
              snippet: 'Provider billed repeated high-intensity claims.',
              document_id: 'claims.csv',
              chunk_index: 4,
            },
          ],
        },
      ],
    }

    render(<RagChatPage />)

    expect(screen.getByLabelText('Citations')).toBeInTheDocument()
    expect(screen.getByText('claims.csv')).toBeInTheDocument()
    expect(screen.getByText('91%')).toBeInTheDocument()
    expect(screen.getByText('Provider billed repeated high-intensity claims.')).toBeInTheDocument()
    expect(screen.getByText('chunk-17 · chunk 4')).toBeInTheDocument()
  })
})
