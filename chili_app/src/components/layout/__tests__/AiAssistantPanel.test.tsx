import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AiAssistantPanel } from '../AiAssistantPanel'

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}))

const dataMocks = vi.hoisted(() => ({
  useAlert: vi.fn(),
  useCase: vi.fn(),
  useDomainConfig: vi.fn(),
  useInvestigationEntity: vi.fn(),
}))

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router')
  return {
    ...actual,
    useNavigate: () => routerMocks.navigate,
  }
})

vi.mock('../../../api/alerts', () => ({ useAlert: dataMocks.useAlert }))
vi.mock('../../../api/cases', () => ({ useCase: dataMocks.useCase }))
vi.mock('../../../api/config', () => ({ useDomainConfig: dataMocks.useDomainConfig }))
vi.mock('../../../api/investigation', () => ({
  useInvestigationEntity: dataMocks.useInvestigationEntity,
}))

describe('AiAssistantPanel', () => {
  beforeEach(() => {
    routerMocks.navigate.mockReset()
    dataMocks.useAlert.mockReturnValue({ data: undefined })
    dataMocks.useCase.mockReturnValue({ data: undefined })
    dataMocks.useInvestigationEntity.mockReturnValue({ data: undefined })
    dataMocks.useDomainConfig.mockReturnValue({
      data: {
        entities: [{ name: 'provider', display_label: 'Provider', properties: {} }],
        relationships: [],
        ui: { display_fields: { provider: { title: 'npi' } } },
      },
    })
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

    expect(
      screen.getByText('Open an alert, case, or entity to ask about it here.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled()
  })

  it('disables sending when no contextual route is active', () => {
    renderPanel('/dashboard')

    expect(
      screen.getByText('Open an alert, case, or entity to ask about it here.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled()
  })

  it('says what it is and where its answers go', () => {
    // Four AI entry points existed with nothing distinguishing them
    // (UXA-407). The rail is the quick ask; RAG Chat is the durable one.
    renderPanel('/alerts?kb=kb-1&alert=alert-1')

    expect(screen.getByText('Quick ask — opens in RAG Chat')).toBeInTheDocument()
  })

  it('explains what it can see when nothing is attached', () => {
    renderPanel('/dashboard')

    expect(
      screen.getByText('Open an alert, case, or entity to ask about it here.'),
    ).toBeInTheDocument()
  })

  it('names the alert it is attached to instead of showing its id', () => {
    dataMocks.useAlert.mockReturnValue({
      data: {
        alert: { title: 'Outlier billing concentration', entity_label: 'Redwood DME Group' },
      },
    })

    renderPanel('/alerts?kb=kb-1&alert=ede44288-b501-4bb8-a50b-ef142bc12be7')

    expect(
      screen.getByText('Outlier billing concentration · Redwood DME Group'),
    ).toBeInTheDocument()
    expect(screen.queryByText(/ede44288/)).not.toBeInTheDocument()
  })

  it('names the case it is attached to instead of showing its id', () => {
    dataMocks.useCase.mockReturnValue({
      data: { case: { title: 'Redwood DME escalation' } },
    })

    renderPanel('/cases?kb=kb-1&case=6deaa96f-bc68-449a-9c31-e14cb996ee3a')

    expect(screen.getByText('Redwood DME escalation')).toBeInTheDocument()
    expect(screen.queryByText(/6deaa96f/)).not.toBeInTheDocument()
  })

  it('names the entity through the configured display field', () => {
    dataMocks.useInvestigationEntity.mockReturnValue({
      data: {
        entity: { id: 'provider-204', type: 'provider', properties: { npi: '1234567890' } },
      },
    })

    renderPanel('/investigation/provider-204?kb=kb-1')

    expect(screen.getByText('1234567890')).toBeInTheDocument()
  })

  it('keeps the identifier reachable on hover rather than in the copy', () => {
    dataMocks.useAlert.mockReturnValue({
      data: {
        alert: { title: 'Outlier billing concentration', entity_label: 'Redwood DME Group' },
      },
    })

    renderPanel('/alerts?kb=kb-1&alert=ede44288-b501-4bb8-a50b-ef142bc12be7')

    expect(
      screen.getByText('Outlier billing concentration · Redwood DME Group'),
    ).toHaveAttribute('title', 'ede44288-b501-4bb8-a50b-ef142bc12be7')
  })

  it('says what it is attached to even before the lookup resolves', () => {
    renderPanel('/alerts?kb=kb-1&alert=ede44288-b501-4bb8-a50b-ef142bc12be7')

    expect(screen.getByText('Attached to the selected alert')).toBeInTheDocument()
    expect(screen.queryByText(/ede44288/)).not.toBeInTheDocument()
  })
})
