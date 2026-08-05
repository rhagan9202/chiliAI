import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type {
  KnowledgeBaseReadinessResponse,
  KnowledgeBaseSummaryResponse,
} from '../../../api/contracts'
import { WorkspaceControl } from '../WorkspaceControl'

const knowledgeBases: KnowledgeBaseSummaryResponse[] = [
  {
    id: 'kb-ready',
    name: 'CMS Ready KB',
    description: '',
    entity_count: 25,
    relationship_count: 40,
    document_count: 3,
    status: 'ready',
    created_at: '2026-08-05T12:00:00Z',
    updated_at: null,
    domain: 'medicare_fraud',
  },
  {
    id: 'kb-building',
    name: 'CMS Building KB',
    description: '',
    entity_count: 0,
    relationship_count: 0,
    document_count: 1,
    status: 'building',
    created_at: '2026-08-04T12:00:00Z',
    updated_at: null,
    domain: 'medicare_fraud',
  },
]

function readiness(
  overrides: Partial<KnowledgeBaseReadinessResponse> = {},
): KnowledgeBaseReadinessResponse {
  return {
    active_domain_name: 'medicare_fraud',
    blockers: [],
    components: {
      knowledge_base: {
        blockers: [],
        details: {},
        label: 'Knowledge base',
        status: 'ready',
        summary: 'Knowledge base is ready.',
        warnings: [],
      },
    },
    knowledge_base: {
      created_at: '2026-08-05T12:00:00Z',
      document_count: 3,
      entity_count: 25,
      id: 'kb-ready',
      name: 'CMS Ready KB',
      relationship_count: 40,
      status: 'ready',
    },
    ready: true,
    warnings: [],
    ...overrides,
  }
}

describe('WorkspaceControl', () => {
  it('renders the active KB selector and reports selection changes', () => {
    const onSelect = vi.fn()

    render(
      <WorkspaceControl
        activeKnowledgeBaseId="kb-ready"
        isError={false}
        isLoading={false}
        knowledgeBases={knowledgeBases}
        onSelectKnowledgeBase={onSelect}
        readiness={readiness()}
        readinessError={false}
        readinessLoading={false}
      />,
    )

    const selector = screen.getByLabelText('Active knowledge base')
    expect(selector).toHaveValue('kb-ready')

    fireEvent.change(selector, { target: { value: 'kb-building' } })

    expect(onSelect).toHaveBeenCalledWith('kb-building')
  })

  it('shows blocked readiness details without exposing credentials', () => {
    const blockedReadiness = readiness({
      blockers: [
        {
          action: 'Register a connector.',
          code: 'no_connectors',
          component: 'connectors',
          message: 'No connectors are configured.',
        },
      ],
      components: {
        connectors: {
          blockers: [
            {
              action: 'Register a connector.',
              code: 'no_connectors',
              component: 'connectors',
              message: 'No connectors are configured.',
            },
          ],
          details: { configured_count: 0 },
          label: 'Connectors',
          status: 'blocked',
          summary: 'Connector state blocks readiness.',
          warnings: [],
        },
      },
      ready: false,
    })

    render(
      <WorkspaceControl
        activeKnowledgeBaseId="kb-ready"
        isError={false}
        isLoading={false}
        knowledgeBases={knowledgeBases}
        onSelectKnowledgeBase={vi.fn()}
        readiness={blockedReadiness}
        readinessError={false}
        readinessLoading={false}
      />,
    )

    expect(screen.getByTestId('workspace-readiness-status')).toHaveTextContent('Blocked')
    const details = screen.getByTestId('workspace-readiness-details')
    expect(within(details).getByText('No connectors are configured.')).toBeInTheDocument()
    expect(within(details).getByText('Register a connector.')).toBeInTheDocument()
    expect(details).not.toHaveTextContent('credentials_ref')
    expect(details).not.toHaveTextContent('CMS_CONNECTOR_TOKEN')
  })

  it('renders an explicit no-KB state with a disabled selector', () => {
    render(
      <WorkspaceControl
        activeKnowledgeBaseId={null}
        isError={false}
        isLoading={false}
        knowledgeBases={[]}
        onSelectKnowledgeBase={vi.fn()}
        readiness={undefined}
        readinessError={false}
        readinessLoading={false}
      />,
    )

    expect(screen.getByText('No knowledge base selected')).toBeInTheDocument()
    expect(screen.getByLabelText('Active knowledge base')).toBeDisabled()
  })
})
