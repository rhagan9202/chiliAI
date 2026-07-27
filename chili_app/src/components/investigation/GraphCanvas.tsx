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
  PREDICTED_LINK_COLOR,
  PREDICTED_LINK_DASH,
  MAX_FIT_ZOOM,
  NODE_REL_SIZE,
  clampFitZoom,
  clusterColorFor,
  colorForEntityType,
  communityIdFor,
  graphNodeLabel,
  linkDistanceFor,
  nodeRadiusFor,
  isPredictedRelationship,
  predictedConfidenceFor,
  riskScoreFor,
  sizeForRiskScore,
} from '../../utils/graphStyles'
import styles from './GraphCanvas.module.css'

const HIGHLIGHT_COLOR = '#fbbf24'

export interface GraphNode extends NodeObject {
  id: string
  entity: Entity
  /** Name drawn on the canvas — resolved by the caller so the graph, the
      dossier and the alert feed all say the same thing (UXA-304). */
  label: string
  color: string
  communityColor: string | null
  size: number
}

export interface GraphLink extends LinkObject {
  id: string
  source: string
  target: string
  relationship: Relationship
  predicted: boolean
  confidence: number | null
}

export interface GraphCanvasProps {
  subgraph: SubgraphResult
  selectedEntityId: string | null
  centerEntityId?: string | null
  onSelectNode: (entityId: string) => void
  entityTypes: string[]
  testId?: string
  clusterMode?: boolean
  highlightedEntityIds?: readonly string[]
  /** Resolves a node's on-canvas name. Defaults to the raw entity id. */
  labelFor?: (entity: Entity) => string
}

export function GraphCanvas({
  subgraph,
  selectedEntityId,
  onSelectNode,
  entityTypes,
  testId,
  clusterMode = false,
  highlightedEntityIds,
  labelFor,
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
    const nodes: GraphNode[] = subgraph.nodes.map((entity) => {
      const communityId = communityIdFor(entity)
      return {
        id: entity.id,
        entity,
        label: labelFor ? labelFor(entity) : entity.id,
        color: colorForEntityType(entity.type, entityTypes),
        communityColor: communityId ? clusterColorFor(communityId) : null,
        size: sizeForRiskScore(riskScoreFor(entity)),
      }
    })
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
        predicted: isPredictedRelationship(edge),
        confidence: predictedConfidenceFor(edge),
      }))
    return { nodes, links }
  }, [subgraph, entityTypes, labelFor])

  const highlightedIds = useMemo(
    () => new Set(highlightedEntityIds ?? []),
    [highlightedEntityIds],
  )

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
    if (link) {
      link.distance((edge: { source: GraphNode | string; target: GraphNode | string }) => {
        const valueOf = (end: GraphNode | string) =>
          typeof end === 'string' ? 0 : end.size
        return linkDistanceFor(valueOf(edge.source), valueOf(edge.target))
      })
    }
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
    // zoomToFit has no upper bound: a 2-3 node neighborhood magnifies until the
    // circles swallow their own edges. Pull it back to a readable scale.
    const fitted = graphRef.current.zoom()
    if (fitted > MAX_FIT_ZOOM) {
      graphRef.current.zoom(clampFitZoom(fitted), 300)
    }
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

  const clusterLegend = useMemo(() => {
    const seen = new Map<string, string>()
    graphData.nodes.forEach((node) => {
      const communityId = communityIdFor(node.entity)
      if (communityId && !seen.has(communityId)) {
        seen.set(communityId, clusterColorFor(communityId))
      }
    })
    return Array.from(seen.entries()).map(([communityId, color]) => ({
      communityId,
      color,
    }))
  }, [graphData])

  const legendContent = clusterMode
    ? clusterLegend.map((item) => (
        <div key={item.communityId} className={styles.legendRow}>
          <span className={styles.legendSwatch} style={{ background: item.color }} />
          <span>{item.communityId}</span>
        </div>
      ))
    : legend.map((item) => (
        <div key={item.type} className={styles.legendRow}>
          <span className={styles.legendSwatch} style={{ background: item.color }} />
          <span>{item.type}</span>
        </div>
      ))
  const showLegend =
    hasData && (clusterMode ? clusterLegend.length > 0 : legend.length > 0)
  const showSelectedKey =
    selectedEntityId !== null && graphData.nodes.some((n) => n.id === selectedEntityId)

  return (
    <div className={styles.wrapper}>
      {/* The legend sits above the canvas rather than floating over it: as an
          absolute overlay it covered whichever node the layout happened to
          settle in the top-left corner (UXA-202). */}
      {showLegend && (
        <div className={styles.legend} aria-hidden="true">
          <span className={styles.legendGroupLabel}>Entity type</span>
          {legendContent}
          {showSelectedKey && (
            <span className={`${styles.legendRow} ${styles.legendRowSelected}`}>
              <span className={styles.legendSwatch} style={{ background: '#fbbf24' }} />
              <span>selected</span>
            </span>
          )}
        </div>
      )}
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
      {hasData && isReady && (
        <ForceGraph2D<GraphNode, GraphLink>
          ref={graphRef}
          width={size.width}
          height={size.height}
          graphData={graphData}
          backgroundColor="#0c1222"
          nodeId="id"
          nodeRelSize={NODE_REL_SIZE}
          nodeVal={(node) => node.size}
          nodeLabel={(node) => `${node.entity.type}: ${node.id}`}
          nodeCanvasObjectMode={() => 'after'}
          nodeCanvasObject={(node, ctx, globalScale) => {
            // Hover tooltips are not enough: a static graph with unlabelled
            // circles cannot be read at all (UXA-202). Labels are drawn under
            // each node and hidden when zoomed far out, where they would only
            // collide into noise.
            if (globalScale < 0.5) return
            const label = graphNodeLabel(node.label)
            if (!label) return
            const fontSize = Math.max(10 / globalScale, 3)
            ctx.font = `${fontSize}px 'IBM Plex Sans', system-ui, sans-serif`
            ctx.textAlign = 'center'
            ctx.textBaseline = 'top'
            const offset = nodeRadiusFor(node.size) + fontSize * 0.6
            const x = node.x ?? 0
            const y = (node.y ?? 0) + offset
            ctx.lineWidth = fontSize * 0.35
            ctx.strokeStyle = 'rgba(12, 18, 34, 0.9)'
            ctx.strokeText(label, x, y)
            ctx.fillStyle = '#e2eaf6'
            ctx.fillText(label, x, y)
          }}
          nodeColor={(node) => {
            if (node.id === selectedEntityId || highlightedIds.has(node.id)) {
              return HIGHLIGHT_COLOR
            }
            if (clusterMode && node.communityColor) {
              return node.communityColor
            }
            return node.color
          }}
          linkColor={(link) =>
            link.predicted ? PREDICTED_LINK_COLOR : 'rgba(120, 170, 255, 0.35)'
          }
          linkLineDash={(link) => (link.predicted ? [...PREDICTED_LINK_DASH] : null)}
          linkWidth={1.5}
          linkLabel={(link) =>
            link.predicted && link.confidence !== null
              ? `predicted · ${link.confidence}`
              : link.relationship.type
          }
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
    </div>
  )
}

export { ENTITY_COLOR_PALETTE }
