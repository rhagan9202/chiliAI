import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

import { InvestigationWorkbench } from '../InvestigationWorkbench'
import { useAppStore } from '../../stores/appStore'
import { MockDomainConfigProvider } from '../../test-utils/MockDomainConfigProvider'
import type {
  EntityDetailResponse,
  EntitySearchResponse,
  NeighborhoodResponse,
} from '../../types/api'

// Replace the WebGL force-graph with a list rendering so we can verify
// node/link counts and click behaviour without canvas APIs.
interface MockGraphProps {
  graphData: {
    nodes: Array<{ id: string }>
    links: Array<{ id: string; source: string; target: string }>
  }
  onNodeClick?: (node: { id: string }) => void
}

vi.mock('react-force-graph-2d', () => ({
  default: ({ graphData, onNodeClick }: MockGraphProps) => (
    <div data-testid="force-graph">
      {graphData.nodes.map((node) => (
        <button
          key={node.id}
          type="button"
          data-testid={`graph-node-${node.id}`}
          onClick={() => onNodeClick?.(node)}
        >
          {node.id}
        </button>
      ))}
      <span data-testid="graph-link-count">{graphData.links.length}</span>
      <span data-testid="graph-node-count">{graphData.nodes.length}</span>
    </div>
  ),
}))

class MockResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
;(globalThis as unknown as { ResizeObserver: typeof MockResizeObserver }).ResizeObserver =
  MockResizeObserver

Element.prototype.getBoundingClientRect = function getBoundingRect() {
  return {
    x: 0,
    y: 0,
    width: 800,
    height: 600,
    top: 0,
    right: 800,
    bottom: 600,
    left: 0,
    toJSON: () => ({}),
  } as DOMRect
}

const FIXED_TIME = '2026-04-27T00:00:00Z'

const neighborhoodResponse: NeighborhoodResponse = {
  center_entity_id: 'e-1',
  entities: [
    {
      id: 'e-1',
      type: 'Provider',
      properties: { risk_score: 0.9 },
      metadata: {},
      created_at: FIXED_TIME,
      version: 1,
    },
    {
      id: 'e-2',
      type: 'Claim',
      properties: { risk_score: 0.4 },
      metadata: {},
      created_at: FIXED_TIME,
      version: 1,
    },
  ],
  relationships: [
    {
      id: 'r-1',
      type: 'BILLED',
      source_id: 'e-1',
      target_id: 'e-2',
      properties: {},
      created_at: FIXED_TIME,
      version: 1,
    },
  ],
}

const entityResponse: EntityDetailResponse = {
  entity: neighborhoodResponse.entities[0],
}

const entitySearchResponse: EntitySearchResponse = {
  items: [neighborhoodResponse.entities[1]],
  total: 1,
}

const knowledgeBaseListResponse = {
  items: [
    {
      id: 'kb-1',
      name: 'Investigation KB',
      description: 'fixture',
      entity_count: 2,
      relationship_count: 1,
      document_count: 1,
      status: 'ready',
      created_at: FIXED_TIME,
      updated_at: null,
    },
  ],
  total: 1,
}

function makeWrapper(initialEntries: string[]): {
  Wrapper: (props: { children: ReactNode }) => React.ReactElement
} {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }): React.ReactElement {
    return (
      <MockDomainConfigProvider
        config={{
          entities: [
            {
              name: 'Provider',
              display_label: 'Provider',
              icon: 'building',
              properties: {},
            },
            {
              name: 'Claim',
              display_label: 'Claim',
              icon: 'file',
              properties: {},
            },
          ],
        }}
      >
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={initialEntries}>
            {children}
          </MemoryRouter>
        </QueryClientProvider>
      </MockDomainConfigProvider>
    )
  }
  return { Wrapper }
}

describe('InvestigationWorkbench', () => {
  const realFetch = global.fetch

  beforeEach(() => {
    useAppStore.setState({
      sidebarOpen: true,
      selectedEntityId: null,
      activeKnowledgeBaseId: null,
    })
  })

  afterEach(() => {
    global.fetch = realFetch
    vi.restoreAllMocks()
  })

  it('seeds selectedEntityId/activeKnowledgeBaseId from URL params and renders subgraph', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL): Promise<Response> => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/neighborhood')) {
        return Promise.resolve(
          new Response(JSON.stringify(neighborhoodResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        )
      }
      if (url.includes('/investigation/entities/')) {
        return Promise.resolve(
          new Response(JSON.stringify(entityResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        )
      }
      if (url.endsWith('/knowledgebases')) {
        return Promise.resolve(
          new Response(JSON.stringify(knowledgeBaseListResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        )
      }
      return Promise.resolve(new Response('{}', { status: 200 }))
    })
    global.fetch = fetchMock as unknown as typeof fetch

    const { Wrapper } = makeWrapper([
      '/investigation?kb_id=kb-1&entity_id=e-1',
    ])
    render(
      <Wrapper>
        <InvestigationWorkbench />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('graph-node-count').textContent).toBe('2')
    })
    expect(screen.getByTestId('graph-link-count').textContent).toBe('1')
    expect(useAppStore.getState().selectedEntityId).toBe('e-1')
    expect(useAppStore.getState().activeKnowledgeBaseId).toBe('kb-1')
  })

  it('clicking a graph node updates selectedEntityId in the Zustand store', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL): Promise<Response> => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.includes('/neighborhood')) {
        return Promise.resolve(
          new Response(JSON.stringify(neighborhoodResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        )
      }
      if (url.includes('/investigation/entities/')) {
        return Promise.resolve(
          new Response(JSON.stringify(entityResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        )
      }
      if (url.endsWith('/knowledgebases')) {
        return Promise.resolve(
          new Response(JSON.stringify(knowledgeBaseListResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        )
      }
      return Promise.resolve(new Response('{}', { status: 200 }))
    })
    global.fetch = fetchMock as unknown as typeof fetch

    const { Wrapper } = makeWrapper([
      '/investigation?kb_id=kb-1&entity_id=e-1',
    ])
    render(
      <Wrapper>
        <InvestigationWorkbench />
      </Wrapper>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('graph-node-e-2')).toBeInTheDocument()
    })
    await userEvent.click(screen.getByTestId('graph-node-e-2'))
    expect(useAppStore.getState().selectedEntityId).toBe('e-2')
  })

  it('searches graph entities and selects a result for neighborhood loading', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL): Promise<Response> => {
      const url = typeof input === 'string' ? input : input.toString()
      if (url.endsWith('/knowledgebases')) {
        return Promise.resolve(
          new Response(JSON.stringify(knowledgeBaseListResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        )
      }
      if (url.includes('/investigation/search')) {
        return Promise.resolve(
          new Response(JSON.stringify(entitySearchResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        )
      }
      if (url.includes('/neighborhood')) {
        return Promise.resolve(
          new Response(JSON.stringify(neighborhoodResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        )
      }
      if (url.includes('/investigation/entities/')) {
        return Promise.resolve(
          new Response(JSON.stringify(entityResponse), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        )
      }
      return Promise.resolve(new Response('{}', { status: 200 }))
    })
    global.fetch = fetchMock as unknown as typeof fetch

    const { Wrapper } = makeWrapper(['/investigation?kb_id=kb-1'])
    render(
      <Wrapper>
        <InvestigationWorkbench />
      </Wrapper>,
    )

    await userEvent.type(screen.getByLabelText('Entity search'), 'claim')
    await userEvent.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() => {
      expect(screen.getByLabelText('Entity search results')).toBeInTheDocument()
    })
    await userEvent.click(screen.getByRole('button', { name: /claim/i }))

    expect(useAppStore.getState().selectedEntityId).toBe('e-2')
  })
})
