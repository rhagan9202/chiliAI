import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAppStore } from '../../stores/appStore'
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
    updated_at?: string
  }>,
  navigate: vi.fn(),
  setSearchParams: vi.fn(),
  searchParams: new URLSearchParams(),
  createConversation: vi.fn(),
  startConversationWithMessage: vi.fn(),
  addMessage: vi.fn(),
  conversationList: [] as Array<{
    id: string
    title: string
    knowledge_base_id: string
    message_count: number
    last_message: string | null
    updated_at: string
  }>,
  conversation: null as null | {
    id: string
    title: string
    knowledge_base_id: string
    messages?: Array<{
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

vi.mock('react-router', () => ({
  Link: ({
    children,
    to,
    ...props
  }: {
    children: React.ReactNode
    to: string | { pathname: string; search?: string }
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
    const href = typeof to === 'string' ? to : `${to.pathname}${to.search ? `?${to.search}` : ''}`
    return (
      <a data-router-link="true" href={href} {...props}>
        {children}
      </a>
    )
  },
  useNavigate: () => mocks.navigate,
  useSearchParams: () => [mocks.searchParams, mocks.setSearchParams],
}))

vi.mock('../../api/config', () => ({
  useDomainConfig: () => ({
    data: {
      domain: { name: 'medicare_fraud' },
      entities: [{ name: 'provider', display_label: 'Provider', properties: {} }],
      relationships: [],
    },
  }),
}))

vi.mock('../../api/knowledgebases', () => ({
  useKnowledgeBases: () => ({
    isLoading: false,
    isError: false,
    data: { items: mocks.knowledgeBases, total: mocks.knowledgeBases.length },
  }),
}))

vi.mock('../../api/rag', () => ({
  isStartConversationPartialError: (error: unknown) =>
    typeof error === 'object' && error != null && 'createdConversation' in error,
  useConversation: () => ({
    isLoading: false,
    isError: false,
    data: mocks.conversation ?? undefined,
  }),
  useConversations: () => ({
    isLoading: false,
    isError: false,
    data: { items: mocks.conversationList, page: { page: 1, page_size: 25, total_items: mocks.conversationList.length } },
  }),
  useCreateConversation: () => ({
    isPending: false,
    mutate: mocks.createConversation,
  }),
  useStartConversationWithMessage: () => ({
    isPending: false,
    mutate: mocks.startConversationWithMessage,
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
  // Most recently updated, so it is the workspace default in the tests below
  // that are about something other than default selection.
  updated_at: '2026-06-01T00:00:00Z',
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
  updated_at: '2026-05-12T00:00:00Z',
}

describe('RagChatPage', () => {
  beforeEach(() => {
    // The active knowledge base is remembered across pages, so it must be reset
    // between tests or one test's selection leaks into the next.
    window.localStorage.clear()
    useAppStore.setState({ activeKnowledgeBaseId: null })
    mocks.knowledgeBases = []
    mocks.navigate.mockReset()
    mocks.setSearchParams.mockReset()
    mocks.searchParams = new URLSearchParams()
    mocks.createConversation.mockReset()
    mocks.startConversationWithMessage.mockReset()
    mocks.addMessage.mockReset()
    mocks.conversation = null
    mocks.conversationList = []
  })

  it('renders a Create Knowledge Base CTA when no KBs exist and navigates on click', async () => {
    render(<RagChatPage />)

    expect(screen.getByText('No knowledge base available')).toBeInTheDocument()

    const cta = screen.getByRole('button', { name: /create knowledge base/i })
    await userEvent.click(cta)

    expect(mocks.navigate).toHaveBeenCalledWith('/knowledge-bases')
  })

  it('gives the page an h1, like every other route', () => {
    // This page builds its own toolbar rather than using SectionHeader, so the
    // one-h1-per-page rule (UXA-205) skipped it and it shipped with none.
    mocks.knowledgeBases = [KB_ONE]

    render(<RagChatPage />)

    expect(screen.getByRole('heading', { level: 1, name: 'RAG Chat' })).toBeInTheDocument()
  })

  it('warns when the selected knowledge base has nothing to answer from', () => {
    // Asking an empty corpus returns nothing, with no explanation of why
    // (UXA-305). Say so before the question is typed.
    mocks.knowledgeBases = [{ ...KB_ONE, status: 'active', document_count: 0, entity_count: 0 }]

    render(<RagChatPage />)

    expect(screen.getByRole('status', { name: 'Knowledge base warning' })).toHaveTextContent(
      /nothing has been ingested/i,
    )
  })

  it('does not warn when the knowledge base holds data', () => {
    mocks.knowledgeBases = [{ ...KB_ONE, status: 'ready', document_count: 3, entity_count: 12 }]

    render(<RagChatPage />)

    expect(screen.queryByRole('status', { name: 'Knowledge base warning' })).not.toBeInTheDocument()
  })

  it('lists past conversations so one can be resumed', () => {
    // The backend persisted conversations and the dev seed created one, but
    // the UI had no way to reach them (UXA-403).
    mocks.knowledgeBases = [KB_ONE]
    mocks.conversationList = [
      {
        id: 'conv-1',
        title: 'Redwood review',
        knowledge_base_id: 'kb-1',
        message_count: 4,
        last_message: 'Because peer deviation is high.',
        updated_at: '2026-07-26T10:00:00Z',
      },
    ]

    render(<RagChatPage />)

    const list = screen.getByRole('list', { name: 'Conversations' })
    expect(within(list).getByText('Redwood review')).toBeInTheDocument()
    expect(within(list).getByText(/Because peer deviation is high/)).toBeInTheDocument()
  })

  it('resumes the conversation that was clicked', async () => {
    mocks.knowledgeBases = [KB_ONE]
    mocks.conversationList = [
      {
        id: 'conv-1',
        title: 'Redwood review',
        knowledge_base_id: 'kb-1',
        message_count: 1,
        last_message: null,
        updated_at: '2026-07-26T10:00:00Z',
      },
    ]

    render(<RagChatPage />)
    await userEvent.click(screen.getByRole('button', { name: /Redwood review/ }))

    expect(screen.getByText('Redwood review')).toBeInTheDocument()
  })

  it('offers starter prompts drawn from the domain pack on an empty conversation', () => {
    mocks.knowledgeBases = [KB_ONE]

    render(<RagChatPage />)

    expect(screen.getByRole('button', { name: /Which Provider records look most unusual/ }))
      .toBeInTheDocument()
  })

  it('puts a starter prompt into the composer rather than sending it blind', async () => {
    mocks.knowledgeBases = [KB_ONE]

    render(<RagChatPage />)
    await userEvent.click(
      screen.getByRole('button', { name: /Which Provider records look most unusual/ }),
    )

    expect(screen.getByPlaceholderText(/Ask the investigation assistant/)).toHaveValue(
      'Which Provider records look most unusual, and why?',
    )
  })

  it('renders an option for each KB and defaults to the workspace knowledge base', () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]

    render(<RagChatPage />)

    const select = screen.getByLabelText('Knowledge base') as HTMLSelectElement
    expect(select.value).toBe('kb-1')
    expect(screen.getByRole('option', { name: /Fraud KB · Ready/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Policy KB · Building/ })).toBeInTheDocument()
  })

  it('defaults to the most recently updated KB rather than the first listed', () => {
    // Both ready, so recency is the only thing that can decide.
    mocks.knowledgeBases = [
      { ...KB_ONE, status: 'ready', updated_at: '2026-01-01T00:00:00Z' },
      { ...KB_TWO, status: 'ready', updated_at: '2026-07-01T00:00:00Z' },
    ]

    render(<RagChatPage />)

    const select = screen.getByLabelText('Knowledge base') as HTMLSelectElement
    expect(select.value).toBe('kb-2')
  })

  it('reuses the knowledge base remembered from another page', () => {
    useAppStore.setState({ activeKnowledgeBaseId: 'kb-2' })
    mocks.knowledgeBases = [KB_ONE, KB_TWO]

    render(<RagChatPage />)

    const select = screen.getByLabelText('Knowledge base') as HTMLSelectElement
    expect(select.value).toBe('kb-2')
  })

  it('honors the ?kb=... URL parameter when it matches an existing KB', () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]
    mocks.searchParams = new URLSearchParams('kb=kb-2')

    render(<RagChatPage />)

    const select = screen.getByLabelText('Knowledge base') as HTMLSelectElement
    expect(select.value).toBe('kb-2')
  })

  it('prefills launch context and starts a contextual alert thread', async () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]
    mocks.searchParams = new URLSearchParams(
      'kb=kb-1&source=alert&alert=alert-1&entity=provider-204&evidence=evidence-1&q=Why+is+this+high+risk%3F',
    )

    render(<RagChatPage />)

    expect(await screen.findByLabelText('Knowledge base')).toHaveValue('kb-1')
    expect(screen.getByDisplayValue('Why is this high risk?')).toBeInTheDocument()
    expect(screen.getByText('alert')).toBeInTheDocument()
    expect(screen.getByText('alert-1')).toBeInTheDocument()
    expect(screen.getByText('provider-204')).toBeInTheDocument()
    expect(screen.getByText('evidence-1')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /start with this context/i }))

    expect(mocks.startConversationWithMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        knowledge_base_id: 'kb-1',
        title: 'Alert investigation',
        content: 'Why is this high risk?',
        filters: expect.objectContaining({
          source_type: 'alert',
          alert_id: 'alert-1',
          entity_id: 'provider-204',
          evidence_pack_id: 'evidence-1',
        }),
      }),
      expect.objectContaining({
        onSuccess: expect.any(Function),
      }),
    )
  })

  it('refreshes the draft when the launch question changes on the mounted route', () => {
    mocks.knowledgeBases = [KB_ONE]
    mocks.searchParams = new URLSearchParams('kb=kb-1&q=First+question')

    const { rerender } = render(<RagChatPage />)

    expect(screen.getByDisplayValue('First question')).toBeInTheDocument()

    mocks.searchParams = new URLSearchParams('kb=kb-1&q=Second+question')
    rerender(<RagChatPage />)

    expect(screen.getByDisplayValue('Second question')).toBeInTheDocument()
  })

  it('clears the consumed launch question after contextual start succeeds', async () => {
    mocks.knowledgeBases = [KB_ONE]
    mocks.searchParams = new URLSearchParams(
      'kb=kb-1&source=alert&alert=alert-1&q=Why+is+this+high+risk%3F',
    )
    mocks.conversation = {
      id: 'conversation-1',
      title: 'Alert investigation',
      knowledge_base_id: 'kb-1',
      messages: [],
    }
    mocks.startConversationWithMessage.mockImplementation((_payload, options) => {
      options?.onSuccess?.(mocks.conversation)
    })

    render(<RagChatPage />)

    await userEvent.click(screen.getByRole('button', { name: /start with this context/i }))

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Ask the investigation assistant about an entity, alert, or evidence trail')).toHaveValue('')
    })
    expect(screen.getByRole('button', { name: /^send$/i })).toBeDisabled()
  })

  it('recovers a created contextual thread when adding the first message fails', async () => {
    mocks.knowledgeBases = [KB_ONE]
    mocks.searchParams = new URLSearchParams(
      'kb=kb-1&source=case&case=case-7&q=Summarize+the+case',
    )
    mocks.conversation = {
      id: 'conversation-1',
      title: 'Case investigation',
      knowledge_base_id: 'kb-1',
      messages: [],
    }
    mocks.startConversationWithMessage.mockImplementation((_payload, options) => {
      options?.onError?.({
        createdConversation: mocks.conversation,
      })
    })

    render(<RagChatPage />)

    await userEvent.click(screen.getByRole('button', { name: /start with this context/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^send$/i })).toBeEnabled()
    })
    expect(
      screen.getByText('The conversation was created, but the first message failed. Review it and send again.'),
    ).toBeInTheDocument()
    expect(screen.getByDisplayValue('Summarize the case')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /^send$/i }))

    expect(mocks.addMessage).toHaveBeenCalledWith({
      content: 'Summarize the case',
      include_graph_context: true,
      filters: expect.objectContaining({
        source_type: 'case',
        case_id: 'case-7',
      }),
    })
  })

  it('falls back to the workspace knowledge base when ?kb=... is unknown', () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]
    mocks.searchParams = new URLSearchParams('kb=missing')

    render(<RagChatPage />)

    const select = screen.getByLabelText('Knowledge base') as HTMLSelectElement
    expect(select.value).toBe('kb-1')
  })

  it('does not infer a KB for contextual launches that omit kb', () => {
    mocks.knowledgeBases = [KB_TWO]
    mocks.searchParams = new URLSearchParams(
      'source=housing&installation=edwards&q=Summarize+housing+supply+risk.',
    )

    render(<RagChatPage />)

    expect(screen.getByText('No knowledge base available')).toBeInTheDocument()
    expect(screen.queryByLabelText('Knowledge base')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /start with this context/i })).not.toBeInTheDocument()
    expect(mocks.startConversationWithMessage).not.toHaveBeenCalled()
  })

  it('updates the URL params when the user picks a different KB', async () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]

    render(<RagChatPage />)

    await userEvent.selectOptions(screen.getByLabelText('Knowledge base'), 'kb-2')

    expect(mocks.setSearchParams).toHaveBeenCalledTimes(1)
    // The shared setter updates the URL through a functional updater so it
    // never clobbers other query params (launch context, case id, ...).
    const updater = mocks.setSearchParams.mock.calls[0][0] as (
      current: URLSearchParams,
    ) => URLSearchParams
    expect(updater(new URLSearchParams()).get('kb')).toBe('kb-2')
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

  it('links citations to entity investigation context when citation entity metadata exists', () => {
    mocks.knowledgeBases = [KB_ONE]
    mocks.searchParams = new URLSearchParams('kb=kb-1&source=alert&alert=alert-1')
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
              entity_id: 'provider-204',
            },
          ],
        },
      ],
    }

    render(<RagChatPage />)

    const link = screen.getByRole('link', {
      name: /open citation context.*claims\.csv.*chunk-17/i,
    })
    expect(link).toHaveAttribute('data-router-link', 'true')
    expect(link).toHaveAttribute(
      'href',
      '/investigation/provider-204?kb=kb-1',
    )
  })

  it('links citations to the launch alert when no entity target exists', () => {
    mocks.knowledgeBases = [KB_ONE]
    mocks.searchParams = new URLSearchParams('kb=kb-1&source=alert&alert=alert-1')
    mocks.conversation = {
      id: 'conversation-1',
      title: 'Alert investigation',
      knowledge_base_id: 'kb-1',
      messages: [
        {
          id: 'message-1',
          role: 'assistant',
          content: 'Alert context explains the anomaly.',
          created_at: '2026-05-12T00:00:00Z',
          citation_ids: ['chunk-18'],
          citations: [
            {
              record_id: 'record-1',
              content_id: 'chunk-18',
              score: 0.83,
              snippet: 'Alert details include repeated billing spikes.',
              document_id: 'alerts.csv',
              chunk_index: 1,
            },
          ],
        },
      ],
    }

    render(<RagChatPage />)

    expect(
      screen.getByRole('link', {
        name: /open citation context.*alerts\.csv.*chunk-18/i,
      }),
    ).toHaveAttribute(
      'href',
      '/alerts?alert=alert-1',
    )
  })

  it('links citations to the launch case when no entity target exists', () => {
    mocks.knowledgeBases = [KB_ONE]
    mocks.searchParams = new URLSearchParams('kb=kb-1&source=case&case=case-1')
    mocks.conversation = {
      id: 'conversation-1',
      title: 'Case investigation',
      knowledge_base_id: 'kb-1',
      messages: [
        {
          id: 'message-1',
          role: 'assistant',
          content: 'Case context explains the anomaly.',
          created_at: '2026-05-12T00:00:00Z',
          citation_ids: ['chunk-19'],
          citations: [
            {
              record_id: 'record-2',
              content_id: 'chunk-19',
              score: 0.77,
              snippet: 'Case notes mention escalation history.',
              document_id: 'case-notes.md',
              chunk_index: 2,
            },
          ],
        },
      ],
    }

    render(<RagChatPage />)

    expect(
      screen.getByRole('link', {
        name: /open citation context.*case-notes\.md.*chunk-19/i,
      }),
    ).toHaveAttribute(
      'href',
      '/cases?kb=kb-1&case=case-1',
    )
  })

  it('renders conversations that omit messages as an empty thread', () => {
    mocks.knowledgeBases = [KB_ONE]
    mocks.conversation = {
      id: 'conversation-1',
      title: 'Investigation thread',
      knowledge_base_id: 'kb-1',
    }

    render(<RagChatPage />)

    expect(screen.getByText('Investigation thread')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^send$/i })).toBeDisabled()
  })

  it('keeps duplicate-content citations as distinct link instances without key collisions', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    mocks.knowledgeBases = [KB_ONE]
    mocks.searchParams = new URLSearchParams('kb=kb-1&source=alert&alert=alert-1')
    mocks.conversation = {
      id: 'conversation-1',
      title: 'Investigation thread',
      knowledge_base_id: 'kb-1',
      messages: [
        {
          id: 'message-1',
          role: 'assistant',
          content: 'Two chunks support this answer.',
          created_at: '2026-05-12T00:00:00Z',
          citation_ids: ['chunk-shared'],
          citations: [
            {
              record_id: 'record-1',
              content_id: 'chunk-shared',
              score: 0.91,
              snippet: 'First cited passage.',
              document_id: 'claims.csv',
              chunk_index: 1,
            },
            {
              record_id: 'record-2',
              content_id: 'chunk-shared',
              score: 0.87,
              snippet: 'Second cited passage.',
              document_id: 'claims.csv',
              chunk_index: 2,
            },
          ],
        },
      ],
    }

    try {
      render(<RagChatPage />)

      expect(
        screen.getByRole('link', {
          name: /open citation context.*claims\.csv.*chunk-shared.*record-1.*chunk 1/i,
        }),
      ).toBeInTheDocument()
      expect(
        screen.getByRole('link', {
          name: /open citation context.*claims\.csv.*chunk-shared.*record-2.*chunk 2/i,
        }),
      ).toBeInTheDocument()
      expect(
        consoleError.mock.calls.some((call) =>
          call.some(
            (value) =>
              typeof value === 'string' &&
              value.includes('Encountered two children with the same key'),
          ),
        ),
      ).toBe(false)
    } finally {
      consoleError.mockRestore()
    }
  })

  it('keeps citations non-clickable when no navigation target exists', () => {
    mocks.knowledgeBases = [KB_ONE]
    mocks.searchParams = new URLSearchParams('kb=kb-1')
    mocks.conversation = {
      id: 'conversation-1',
      title: 'Investigation thread',
      knowledge_base_id: 'kb-1',
      messages: [
        {
          id: 'message-1',
          role: 'assistant',
          content: 'General context explains the anomaly.',
          created_at: '2026-05-12T00:00:00Z',
          citation_ids: ['chunk-20'],
          citations: [
            {
              record_id: 'record-3',
              content_id: 'chunk-20',
              score: 0.64,
              snippet: 'General policy guidance applies.',
              document_id: 'policy.md',
              chunk_index: 5,
            },
          ],
        },
      ],
    }

    render(<RagChatPage />)

    expect(screen.queryByRole('link', { name: /open citation context/i })).not.toBeInTheDocument()
    expect(screen.getByText('policy.md')).toBeInTheDocument()
    expect(screen.getByText('64%')).toBeInTheDocument()
    expect(screen.getByText('General policy guidance applies.')).toBeInTheDocument()
    expect(screen.getByText('chunk-20 · chunk 5')).toBeInTheDocument()
  })

  it('keeps manual send on the existing add-message path', async () => {
    mocks.knowledgeBases = [KB_ONE]
    mocks.conversation = {
      id: 'conversation-1',
      title: 'Investigation thread',
      knowledge_base_id: 'kb-1',
      messages: [],
    }
    mocks.createConversation.mockImplementation((_payload, options) => {
      options?.onSuccess?.(mocks.conversation)
    })

    render(<RagChatPage />)

    await userEvent.click(screen.getByRole('button', { name: /new conversation/i }))
    await userEvent.type(
      screen.getByPlaceholderText('Ask the investigation assistant about an entity, alert, or evidence trail'),
      'What does this claim show?',
    )
    await userEvent.click(screen.getByRole('button', { name: /^send$/i }))

    expect(mocks.addMessage).toHaveBeenCalledWith({
      content: 'What does this claim show?',
      include_graph_context: true,
      filters: {},
    })
    expect(mocks.startConversationWithMessage).not.toHaveBeenCalled()
  })
})
