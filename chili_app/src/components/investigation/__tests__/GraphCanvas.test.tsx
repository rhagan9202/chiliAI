import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { GraphCanvas } from '../GraphCanvas'
import type { GraphNode, GraphLink } from '../GraphCanvas'
import type { Entity, Relationship, SubgraphResult } from '../../../types/api'

// Replace the WebGL/canvas-backed library with a deterministic test double
// that surfaces nodes/links as semantic DOM so we can assert render counts
// and exercise the click handler without a real canvas.
interface ForceGraphTestProps {
  graphData: { nodes: GraphNode[]; links: GraphLink[] }
  onNodeClick?: (node: GraphNode) => void
  linkLabel?: (link: GraphLink) => string
}

vi.mock('react-force-graph-2d', () => ({
  default: ({ graphData, onNodeClick, linkLabel }: ForceGraphTestProps) => (
    <div data-testid="force-graph">
      <ul data-testid="force-graph-nodes">
        {graphData.nodes.map((node) => (
          <li key={node.id}>
            <button
              type="button"
              data-testid={`graph-node-${node.id}`}
              onClick={() => onNodeClick?.(node)}
            >
              {node.entity.type}:{node.id}
            </button>
          </li>
        ))}
      </ul>
      <ul data-testid="force-graph-links">
        {graphData.links.map((link) => (
          <li
            key={link.id}
            data-testid={`graph-link-${link.id}`}
            data-label={linkLabel?.(link) ?? ''}
          >
            {link.source}-&gt;{link.target}
          </li>
        ))}
      </ul>
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

const FIXED_TIME = '2026-04-27T00:00:00Z'

function makeEntity(
  id: string,
  type: string,
  riskScore: number = 0,
): Entity {
  return {
    id,
    type,
    properties: { risk_score: riskScore },
    metadata: {},
    created_at: FIXED_TIME,
    version: 1,
  }
}

function makeRelationship(
  id: string,
  type: string,
  source: string,
  target: string,
): Relationship {
  return {
    id,
    type,
    source_id: source,
    target_id: target,
    properties: {},
    created_at: FIXED_TIME,
    version: 1,
  }
}

function makeSubgraph(): SubgraphResult {
  return {
    nodes: [
      makeEntity('e1', 'Provider', 0.9),
      makeEntity('e2', 'Beneficiary', 0.2),
      makeEntity('e3', 'Claim', 0.5),
    ],
    edges: [
      makeRelationship('r1', 'BILLED', 'e1', 'e3'),
      makeRelationship('r2', 'RECEIVED', 'e2', 'e3'),
    ],
  }
}

function setRectMock(width = 800, height = 600): void {
  Element.prototype.getBoundingClientRect = function getBoundingClientRectStub() {
    return {
      x: 0,
      y: 0,
      width,
      height,
      top: 0,
      right: width,
      bottom: height,
      left: 0,
      toJSON: () => ({}),
    } as DOMRect
  }
}

describe('GraphCanvas', () => {
  it('renders one node per subgraph entity and one link per relationship', () => {
    setRectMock()
    render(
      <GraphCanvas
        subgraph={makeSubgraph()}
        selectedEntityId={null}
        onSelectNode={() => undefined}
        entityTypes={['Provider', 'Beneficiary', 'Claim']}
      />,
    )
    const nodes = screen.getByTestId('force-graph-nodes').children
    const links = screen.getByTestId('force-graph-links').children
    expect(nodes).toHaveLength(3)
    expect(links).toHaveLength(2)
  })

  it('exposes relationship type via linkLabel for hover tooltips', () => {
    setRectMock()
    render(
      <GraphCanvas
        subgraph={makeSubgraph()}
        selectedEntityId={null}
        onSelectNode={() => undefined}
        entityTypes={['Provider', 'Beneficiary', 'Claim']}
      />,
    )
    expect(screen.getByTestId('graph-link-r1').dataset.label).toBe('BILLED')
    expect(screen.getByTestId('graph-link-r2').dataset.label).toBe('RECEIVED')
  })

  it('invokes onSelectNode with entity id when a node is clicked', async () => {
    setRectMock()
    const onSelect = vi.fn()
    render(
      <GraphCanvas
        subgraph={makeSubgraph()}
        selectedEntityId={null}
        onSelectNode={onSelect}
        entityTypes={['Provider', 'Beneficiary', 'Claim']}
      />,
    )
    await userEvent.click(screen.getByTestId('graph-node-e1'))
    expect(onSelect).toHaveBeenCalledWith('e1')
  })

  it('shows a placeholder when the subgraph has no nodes', () => {
    setRectMock()
    render(
      <GraphCanvas
        subgraph={{ nodes: [], edges: [] }}
        selectedEntityId={null}
        onSelectNode={() => undefined}
        entityTypes={[]}
      />,
    )
    expect(
      screen.getByText(/select an entity to load its neighborhood/i),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('force-graph')).not.toBeInTheDocument()
  })
})
