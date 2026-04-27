import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import type {
  ForceGraphMethods,
  LinkObject,
  NodeObject,
} from 'react-force-graph-2d'

import type { Entity, Relationship, SubgraphResult } from '../../types/api'
import {
  ENTITY_COLOR_PALETTE,
  colorForEntityType,
  riskScoreFor,
  sizeForRiskScore,
} from '../../utils/graphStyles'
import styles from './GraphCanvas.module.css'

export interface GraphNode extends NodeObject {
  id: string
  entity: Entity
  color: string
  size: number
}

export interface GraphLink extends LinkObject {
  id: string
  source: string
  target: string
  relationship: Relationship
}

export interface GraphCanvasProps {
  subgraph: SubgraphResult
  selectedEntityId: string | null
  centerEntityId?: string | null
  onSelectNode: (entityId: string) => void
  entityTypes: string[]
  testId?: string
}

interface HoverState {
  x: number
  y: number
  label: string
}

export function GraphCanvas({
  subgraph,
  selectedEntityId,
  centerEntityId,
  onSelectNode,
  entityTypes,
  testId,
}: GraphCanvasProps): React.ReactElement {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const graphRef =
    useRef<ForceGraphMethods<GraphNode, GraphLink> | undefined>(undefined)
  const [size, setSize] = useState<{ width: number; height: number }>({
    width: 0,
    height: 0,
  })
  const [hover, setHover] = useState<HoverState | null>(null)

  useLayoutEffect(() => {
    const node = containerRef.current
    if (!node) return undefined
    const update = (): void => {
      const rect = node.getBoundingClientRect()
      const width = Math.max(0, Math.floor(rect.width))
      const height = Math.max(0, Math.floor(rect.height))
      setSize((previous) => {
        if (previous.width === width && previous.height === height) {
          return previous
        }
        return { width, height }
      })
    }
    update()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', update)
      return () => window.removeEventListener('resize', update)
    }
    const observer = new ResizeObserver(update)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const graphData = useMemo(() => {
    const nodes: GraphNode[] = subgraph.nodes.map((entity) => ({
      id: entity.id,
      entity,
      color: colorForEntityType(entity.type, entityTypes),
      size: sizeForRiskScore(riskScoreFor(entity)),
    }))
    const validIds = new Set(nodes.map((node) => node.id))
    const links: GraphLink[] = subgraph.edges
      .filter(
        (edge) =>
          validIds.has(edge.source_id) && validIds.has(edge.target_id),
      )
      .map((edge) => ({
        id: edge.id,
        source: edge.source_id,
        target: edge.target_id,
        relationship: edge,
      }))
    return { nodes, links }
  }, [subgraph, entityTypes])

  useEffect(() => {
    if (!graphRef.current) return
    if (graphData.nodes.length === 0) return
    graphRef.current.zoomToFit(400, 80)
  }, [graphData])

  useEffect(() => {
    if (!graphRef.current || !centerEntityId) return
    const target = graphData.nodes.find((node) => node.id === centerEntityId)
    if (!target) return
    const { x, y } = target
    if (typeof x === 'number' && typeof y === 'number') {
      graphRef.current.centerAt(x, y, 400)
      graphRef.current.zoom(2.5, 400)
    }
  }, [centerEntityId, graphData])

  const legend = useMemo(() => {
    const seen = new Set<string>()
    return graphData.nodes
      .map((node) => node.entity.type)
      .filter((type) => {
        if (seen.has(type)) return false
        seen.add(type)
        return true
      })
      .map((type) => ({
        type,
        color: colorForEntityType(type, entityTypes),
      }))
  }, [graphData, entityTypes])

  const isReady = size.width > 0 && size.height > 0
  const hasData = graphData.nodes.length > 0

  return (
    <div
      ref={containerRef}
      className={styles.container}
      data-testid={testId ?? 'graph-canvas'}
    >
      {!hasData && (
        <div className={styles.placeholder} role="status">
          No graph data — select an entity to load its neighborhood.
        </div>
      )}
      {hasData && legend.length > 0 && (
        <div className={styles.legend} aria-hidden="true">
          {legend.map((item) => (
            <div key={item.type} className={styles.legendRow}>
              <span
                className={styles.legendSwatch}
                style={{ background: item.color }}
              />
              <span>{item.type}</span>
            </div>
          ))}
        </div>
      )}
      {hasData && isReady && (
        <ForceGraph2D<GraphNode, GraphLink>
          ref={graphRef}
          width={size.width}
          height={size.height}
          graphData={graphData}
          nodeId="id"
          nodeVal={(node) => node.size}
          nodeLabel={(node) => `${node.entity.type}: ${node.id}`}
          nodeColor={(node) =>
            node.id === selectedEntityId
              ? '#fbbf24'
              : node.color
          }
          linkColor={() => 'rgba(107, 99, 117, 0.55)'}
          linkWidth={1.2}
          linkLabel={(link) => link.relationship.type}
          onNodeClick={(node) => {
            if (typeof node.id === 'string') {
              onSelectNode(node.id)
            }
          }}
          onLinkHover={(link) => {
            if (link) {
              setHover({
                x: 0,
                y: 0,
                label: link.relationship.type,
              })
            } else {
              setHover(null)
            }
          }}
          enableZoomInteraction
          enablePanInteraction
          enableNodeDrag
          minZoom={0.2}
          maxZoom={8}
          cooldownTicks={120}
        />
      )}
      {hover && (
        <div
          className={styles.tooltip}
          style={{ left: 12, bottom: 12 }}
          role="tooltip"
        >
          {hover.label}
        </div>
      )}
    </div>
  )
}

export { ENTITY_COLOR_PALETTE }
