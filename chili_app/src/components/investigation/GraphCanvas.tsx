import {
  useCallback,
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

export function GraphCanvas({
  subgraph,
  selectedEntityId,
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
  // Track whether the initial fit-to-view has run for the current dataset.
  // Avoids resetting user pan/zoom on every node drag reheat.
  const hasInitialFitRef = useRef(false)
  // Holds the latest graphData so handleEngineStop doesn't need to be recreated.
  const graphDataRef = useRef<typeof graphData | null>(null)
  // Guards the one-time d3 force customization so it only runs once per mount.
  const forcesCustomizedRef = useRef(false)
  // Persists pinned node positions (fx/fy) across graphData rebuilds so pins
  // survive entity navigation and layout refreshes.
  const pinnedPositionsRef = useRef<Map<string, { fx: number; fy: number }>>(new Map())

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
    // Keep the ref in sync with the latest graphData so handleEngineStop
    // can read it without causing the callback to be recreated.
    graphDataRef.current = graphData
    // Restore pinned positions onto the new node objects. The d3 simulation
    // reads node.fx/node.fy on every tick, so setting them here (immediately
    // after render) takes effect on the very next simulation step.
    graphData.nodes.forEach((n) => {
      const pin = pinnedPositionsRef.current.get(n.id)
      if (pin !== undefined) {
        n.fx = pin.fx
        n.fy = pin.fy
      }
    })
    // Reset the fit guard whenever the dataset changes so the engine-stop
    // handler performs a smooth final fit on the settled layout.
    hasInitialFitRef.current = false
  }, [graphData])

  // Run once when ForceGraph2D first becomes available. Increase link distance
  // and charge strength so the force layout spreads nodes further apart, giving
  // `zoomToFit` a larger bounding box and producing visible node sizes.
  const isReady = size.width > 0 && size.height > 0
  const hasData = graphData.nodes.length > 0

  useEffect(() => {
    if (!isReady || !hasData || forcesCustomizedRef.current) return
    const g = graphRef.current
    if (!g) return
    forcesCustomizedRef.current = true
    const link = g.d3Force('link')
    if (link) link.distance(50)
    const charge = g.d3Force('charge')
    if (charge) charge.strength(-150)
    g.d3ReheatSimulation()
  }, [isReady, hasData])

  // Record dropped position so it survives entity navigation (new graphData).
  // Because handleEngineStop freezes every node after initial layout, the
  // drag-end callback receives node.fx at the drop position (library does NOT
  // clear fx when initPos.fx was already set). Belt-and-suspenders: also set
  // fx/fy explicitly in case this fires before the first freeze.
  const handleNodeDragEnd = useCallback((node: GraphNode) => {
    // Prefer fx (kept by library when node was already pinned); fall back to x.
    const px =
      typeof node.fx === 'number' ? node.fx : typeof node.x === 'number' ? node.x : undefined
    const py =
      typeof node.fy === 'number' ? node.fy : typeof node.y === 'number' ? node.y : undefined
    if (px !== undefined && py !== undefined) {
      node.fx = px
      node.fy = py
      pinnedPositionsRef.current.set(node.id, { fx: px, fy: py })
    }
  }, [])

  // Fires once the d3 simulation converges. Performs a smooth final fit so
  // every node is visible at its settled position. The guard prevents this from
  // resetting the viewport after every node-drag reheat.
  //
  // After fitting, ALL nodes are frozen at their settled positions by setting
  // fx/fy = x/y. This means every subsequent drag starts with initPos.fx set
  // (not undefined), so the force-graph library's drag-end handler never clears
  // fx/fy — the node stays exactly where the user drops it without needing the
  // simulation to be running.
  const handleEngineStop = useCallback(() => {
    if (!graphRef.current || (graphDataRef.current?.nodes.length ?? 0) === 0) return
    if (hasInitialFitRef.current) return
    hasInitialFitRef.current = true
    graphRef.current.zoomToFit(500, 40)
    graphDataRef.current?.nodes.forEach((n) => {
      if (typeof n.x === 'number' && typeof n.y === 'number') {
        n.fx = n.x
        n.fy = n.y
      }
    })
  }, [])

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

  return (
    <div
      ref={containerRef}
      className={styles.container}
      data-testid={testId ?? 'graph-canvas'}
      onDragStart={(e) => e.preventDefault()}
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
          {selectedEntityId !== null &&
            graphData.nodes.some((n) => n.id === selectedEntityId) && (
              <div className={`${styles.legendRow} ${styles.legendRowSelected}`}>
                <span
                  className={styles.legendSwatch}
                  style={{ background: '#fbbf24' }}
                />
                <span>selected</span>
              </div>
            )}
        </div>
      )}
      {hasData && isReady && (
        <ForceGraph2D<GraphNode, GraphLink>
          ref={graphRef}
          width={size.width}
          height={size.height}
          graphData={graphData}
          backgroundColor="#0c1222"
          nodeId="id"
          nodeRelSize={14}
          nodeVal={(node) => node.size}
          nodeLabel={(node) => `${node.entity.type}: ${node.id}`}
          nodeColor={(node) =>
            node.id === selectedEntityId
              ? '#fbbf24'
              : node.color
          }
          linkColor={() => 'rgba(120, 170, 255, 0.35)'}
          linkWidth={1.5}
          linkLabel={(link) => link.relationship.type}
          onNodeClick={(node) => {
            if (typeof node.id === 'string') {
              onSelectNode(node.id)
            }
          }}
          enableZoomInteraction
          enablePanInteraction
          enableNodeDrag
          onNodeDragEnd={handleNodeDragEnd}
          warmupTicks={200}
          cooldownTicks={1}
          onEngineStop={handleEngineStop}
          minZoom={0.2}
          maxZoom={8}
        />
      )}
    </div>
  )
}

export { ENTITY_COLOR_PALETTE }
