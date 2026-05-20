/**
 * Flow 5b: RAG chat page
 *
 * Verifies that RagChatPage renders the chat interface, allows starting a
 * conversation, and displays the assistant reply after a message is sent.
 *
 * No SSE/streaming is used. The chat endpoints are plain REST:
 *   POST /chat/conversations   → creates a conversation (returns ChatConversationResponse)
 *   POST /chat/conversations/:id/messages → appends a message, returns updated
 *                                            ChatConversationResponse with all messages
 *
 * This page also requires:
 *   GET /knowledgebases        → must return ≥1 item or the page renders "no KB" empty state
 *
 * Mocked endpoints (host-anchored):
 *   GET  http://localhost:5173/api/auth/me                                    → SessionUser
 *   GET  http://localhost:5173/api/config/domain                              → DomainConfig
 *   GET  http://localhost:5173/api/config/features                            → DomainFeatures
 *   GET  http://localhost:5173/api/events/stream                              → SSE stub
 *   GET  http://localhost:5173/api/knowledgebases                             → KnowledgeBaseListResponse
 *   POST http://localhost:5173/api/chat/conversations                         → ChatConversationResponse
 *   POST http://localhost:5173/api/chat/conversations/conv-001/messages       → ChatConversationResponse
 *
 * Endpoint paths verified against:
 *   - createConversation: src/api/rag.ts → apiPost('/chat/conversations', payload)
 *   - addMessage:         src/api/rag.ts → apiPost('/chat/conversations/:id/messages', payload)
 *   - getKnowledgeBases:  src/api/knowledgebases.ts → apiFetch('/knowledgebases')
 *
 * Response shapes verified against:
 *   - ChatConversationResponse → src/api/contracts.ts
 *   - ChatMessageResponse      → src/api/contracts.ts
 *   - KnowledgeBaseListResponse → src/api/contracts.ts
 *
 * Route: /rag-chat → RagChatPage (src/app/router.tsx)
 */

import { test, expect } from '@playwright/test'

import { mockAuthenticatedShell, mockKnowledgeBases } from './helpers/mocks'
import type { FakeKnowledgeBase } from './helpers/mocks'

const API = 'http://localhost:5173/api'

const FAKE_KB: FakeKnowledgeBase = {
  id: 'kb-001',
  name: 'Medicare FY2024',
  description: 'Claims and providers for FY2024 audit.',
  status: 'ready',
  document_count: 12,
  entity_count: 340,
  relationship_count: 890,
  created_at: '2024-01-15T10:00:00Z',
}

/** Minimal ChatConversationResponse with no messages yet — used for createConversation response. */
const EMPTY_CONVERSATION = {
  id: 'conv-001',
  title: 'Investigation thread',
  knowledge_base_id: 'kb-001',
  messages: [],
}

/** ChatConversationResponse after addMessage: user message + assistant reply. */
const CONVERSATION_WITH_REPLY = {
  id: 'conv-001',
  title: 'Investigation thread',
  knowledge_base_id: 'kb-001',
  messages: [
    {
      id: 'msg-001',
      role: 'user' as const,
      content: 'What is the risk profile of Acme Medical Supply?',
      created_at: '2024-05-01T10:00:00Z',
      citation_ids: [],
    },
    {
      id: 'msg-002',
      role: 'assistant' as const,
      content:
        'Based on retrieved evidence, Acme Medical Supply shows elevated billing anomalies.',
      created_at: '2024-05-01T10:00:05Z',
      citation_ids: ['doc-ref-001'],
    },
  ],
}

test.describe('RAG chat page', () => {
  test('renders chat interface and shows "no KB" empty state when no knowledge bases exist', async ({
    page,
  }) => {
    await mockAuthenticatedShell(page)
    await mockKnowledgeBases(page, [])

    await page.goto('/rag-chat')

    await expect(page.getByRole('heading', { name: 'RAG Chat' })).toBeVisible()
    await expect(page.getByText('No knowledge base available')).toBeVisible()
  })

  test('renders chat thread and assistant response after sending a message', async ({ page }) => {
    await mockAuthenticatedShell(page)
    await mockKnowledgeBases(page, [FAKE_KB])

    // POST /chat/conversations → returns the new empty conversation.
    await page.route(`${API}/chat/conversations`, (route) => {
      if (route.request().method() !== 'POST') {
        void route.continue()
        return
      }
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(EMPTY_CONVERSATION),
      })
    })

    // POST /chat/conversations/conv-001/messages → returns conversation with messages.
    await page.route(`${API}/chat/conversations/conv-001/messages`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(CONVERSATION_WITH_REPLY),
      })
    })

    await page.goto('/rag-chat')

    // Page heading.
    await expect(page.getByRole('heading', { name: 'RAG Chat' })).toBeVisible()

    // "Start new thread" button is visible — rendered regardless of conversation state
    // when a knowledge base is available. Source: RagChatPage.tsx.
    const startButton = page.getByRole('button', { name: 'Start new thread' })
    await expect(startButton).toBeVisible()
    await expect(startButton).toBeEnabled()

    // No active conversation yet — empty state is shown.
    await expect(page.getByText('No active conversation')).toBeVisible()

    // Click "Start new thread" — fires createConversationMutation → POST /chat/conversations.
    await startButton.click()

    // After the mutation resolves, conversationId is set and the textarea + Send message
    // button become available. Source: RagChatPage.tsx — Send button is disabled when
    // !conversationId || draft.trim().length === 0.
    const textarea = page.getByPlaceholder(
      'Ask the investigation assistant about an entity, alert, or evidence trail',
    )
    await expect(textarea).toBeVisible()

    // Scope the Send button to .metric-stack (the input card) to avoid matching the
    // AiAssistantPanel's aria-label="Send message" button in the AppShell.
    // Source: RagChatPage renders Send button inside <div class="metric-stack"> in a Card.
    const inputCard = page.locator('.metric-stack')
    const sendButton = inputCard.getByRole('button', { name: 'Send message' })
    // No draft typed yet — button is disabled.
    await expect(sendButton).toBeDisabled()

    // Type a question in the textarea.
    await textarea.fill('What is the risk profile of Acme Medical Supply?')
    await expect(sendButton).toBeEnabled()

    // Click Send — fires addMessageMutation → POST /chat/conversations/conv-001/messages.
    await sendButton.click()

    // After the mutation resolves, the conversation is updated in React Query cache and
    // RagChatPage re-renders with the full message list.
    // User message renders as a .chat-bubble element.
    await expect(
      page.getByText('What is the risk profile of Acme Medical Supply?'),
    ).toBeVisible()

    // Assistant response renders as .chat-bubble--assistant.
    await expect(
      page.getByText('Based on retrieved evidence, Acme Medical Supply shows elevated billing anomalies.'),
    ).toBeVisible()

    // Citation chip renders — ChatMessageResponse.citation_ids: ['doc-ref-001']
    // RagChatPage renders each citation_id as a <Chip label={citationId} />.
    await expect(page.locator('.ui-chip', { hasText: 'doc-ref-001' })).toBeVisible()
  })
})
