import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AiAssistantPanel } from '../AiAssistantPanel'

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => routerMocks.navigate,
  }
})

describe('AiAssistantPanel', () => {
  beforeEach(() => {
    routerMocks.navigate.mockReset()
  })

  const renderPanel = (initialEntry: string) =>
    render(
      <MemoryRouter initialEntries={[initialEntry]}>
        <AiAssistantPanel />
      </MemoryRouter>,
    )

  const askQuestion = async (question: string) => {
    await userEvent.type(screen.getByLabelText('Ask the AI investigator'), question)
    await userEvent.click(screen.getByRole('button', { name: /send message/i }))
  }

  it('sends an investigation entity question to contextual RAG', async () => {
    renderPanel('/investigation/provider-204?kb=kb-1')

    await askQuestion('Why is this high risk?')

    expect(routerMocks.navigate).toHaveBeenCalledWith(
      '/rag-chat?kb=kb-1&source=entity&entity=provider-204&q=Why+is+this+high+risk%3F',
    )
  })

  it('sends an alert question to contextual RAG', async () => {
    renderPanel('/alerts?kb=kb-1&alert=alert-1')

    await askQuestion('Summarize this alert')

    expect(routerMocks.navigate).toHaveBeenCalledWith(
      '/rag-chat?kb=kb-1&source=alert&alert=alert-1&q=Summarize+this+alert',
    )
  })

  it('sends a case question to contextual RAG', async () => {
    renderPanel('/cases?kb=kb-1&case=case-1')

    await askQuestion('What changed?')

    expect(routerMocks.navigate).toHaveBeenCalledWith(
      '/rag-chat?kb=kb-1&source=case&case=case-1&q=What+changed%3F',
    )
  })

  it('preserves current RAG entity context when sending another question', async () => {
    renderPanel('/rag-chat?kb=kb-1&source=entity&entity=provider-204')

    await askQuestion('What evidence supports this?')

    expect(routerMocks.navigate).toHaveBeenCalledWith(
      '/rag-chat?kb=kb-1&source=entity&entity=provider-204&q=What+evidence+supports+this%3F',
    )
  })

  it('treats malformed encoded investigation paths as no context', () => {
    renderPanel('/investigation/%E0%A4%A?kb=kb-1')

    expect(screen.getByText('Open an alert, case, or entity to attach context.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled()
  })

  it('disables sending when no contextual route is active', () => {
    renderPanel('/dashboard')

    expect(screen.getByText('Open an alert, case, or entity to attach context.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled()
  })
})
