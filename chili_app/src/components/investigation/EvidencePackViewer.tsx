import { useMemo, type ReactNode } from 'react'

import type { EvidencePackResponse } from '../../api/contracts'
import type { Entity, SubgraphResult } from '../../types/api'
import { absoluteTime, relativeAge } from '../../utils/relativeTime'
import { AttributionBars } from '../charts/AttributionBars'
import { Card } from '../ui/Card'
import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import { GraphCanvas } from './GraphCanvas'

export interface EvidencePackViewerProps {
  pack: EvidencePackResponse
  /** Neighborhood subgraph to draw the pack's nodes from (re-uses GraphCanvas). */
  subgraph: SubgraphResult
  entityTypes: string[]
  selectedEntityId?: string | null
  onSelectNode?: (entityId: string) => void
  testId?: string
  /** Resolves an entity's on-canvas name; passed straight to {@link GraphCanvas}
      so the pack subgraph names entities exactly like the dossier (UXA-304). */
  labelFor?: (entity: Entity) => string
  /** Controls rendered beside the header — export, attach to case (UXA-405).
      The viewer stays presentational: it does not know what a case is. */
  actions?: ReactNode
}

/** `peer_deviation` -> `Peer deviation`: score keys are data, not copy. */
function humanizeScoreName(name: string): string {
  const words = name.replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/**
 * Render a persisted evidence pack (BL-006): reasoning, contributing items, a
 * metric snapshot (scores + confidence), policy citations, and the explanatory
 * subgraph via {@link GraphCanvas}. The pack stores node ids only, so the
 * subgraph is resolved by filtering the supplied neighborhood to those ids.
 */
export function EvidencePackViewer({
  pack,
  subgraph,
  entityTypes,
  selectedEntityId = null,
  onSelectNode,
  testId = 'evidence-pack-viewer',
  labelFor,
  actions,
}: EvidencePackViewerProps) {
  const packSubgraph = useMemo<SubgraphResult>(() => {
    const packNodeIds = new Set(pack.subgraph_node_ids)
    const nodes = subgraph.nodes.filter((node) => packNodeIds.has(node.id))
    if (nodes.length === 0) {
      // No overlap with the loaded neighborhood; fall back to the neighborhood
      // so the analyst still sees graph context for the alert.
      return subgraph
    }
    const nodeIds = new Set(nodes.map((node) => node.id))
    const edges = subgraph.edges.filter(
      (edge) => nodeIds.has(edge.source_id) && nodeIds.has(edge.target_id),
    )
    return { nodes, edges }
  }, [pack.subgraph_node_ids, subgraph])

  const scoreEntries = Object.entries(pack.scores ?? {})
  const items = pack.items ?? []
  const policyCitations = pack.policy_citations ?? []
  const narrativeSections = pack.narrative_sections ?? []
  const sourceDocuments = pack.source_documents ?? []
  const attribution = pack.attribution ?? []

  return (
    <Card>
      <div className="metric-stack" data-testid={testId}>
        <div className="metric-row">
          <strong>Evidence pack</strong>
          {/* Supplied by the page, because what you can do with a pack depends
              on where you are looking at it: the Alert Feed has an alert to
              attach, the workbench does not (UXA-405). */}
          {actions ? (
            <div className="page-actions-inline" data-testid="evidence-pack-actions">
              {actions}
            </div>
          ) : null}
        </div>

        <div className="callout--ai" data-testid="evidence-narrative">
          <div className="evidence-pack__attribution">
            <span className="flag-label" style={{ color: 'var(--c-cyan)' }}>
              ◆ AI NARRATIVE
            </span>
            {/* An explanation with no date and no sources is an unattributed
                assertion (UXA-405). */}
            <span className="alert-row-card__age" title={absoluteTime(pack.created_at)}>
              Generated {relativeAge(pack.created_at)}
            </span>
          </div>
          <p className="page-copy-block" style={{ fontSize: '14px' }}>
            {pack.reasoning}
          </p>
          {narrativeSections.map((section) => (
            <div className="metric-row metric-row--stacked" key={section.heading + section.body}>
              <strong>{section.heading}</strong>
              <span className="metric-row__label">{section.body}</span>
            </div>
          ))}
        </div>

        {/* The alert card's confidence and this pack's are different numbers
            answering different questions; say which is which (UXA-303). */}
        <div className="alert-row-card__meta">
          <Chip
            label={`Evidence confidence ${(pack.confidence * 100).toFixed(0)}%`}
            title="How well the collected evidence supports this explanation. The alert's own confidence scores the detection that raised it."
            tone="info"
          />
          {scoreEntries.map(([name, value]) => (
            <Chip
              key={name}
              label={`${humanizeScoreName(name)} ${(value * 100).toFixed(0)}%`}
              tone="default"
            />
          ))}
        </div>

        {sourceDocuments.length > 0 ? (
          <div className="metric-row metric-row--stacked">
            <strong>Drawn from</strong>
            <div className="alert-row-card__meta">
              {sourceDocuments.map((source) => (
                <Chip key={source} label={source} tone="default" />
              ))}
            </div>
          </div>
        ) : null}

        {attribution.length > 0 ? <AttributionBars attribution={attribution} /> : null}

        {packSubgraph.nodes.length > 0 ? (
          <div className="investigation-graph-canvas">
            <GraphCanvas
              subgraph={packSubgraph}
              selectedEntityId={selectedEntityId}
              centerEntityId={selectedEntityId}
              entityTypes={entityTypes}
              labelFor={labelFor}
              onSelectNode={onSelectNode ?? (() => undefined)}
              testId="evidence-pack-subgraph"
            />
          </div>
        ) : (
          <EmptyState description="No subgraph nodes are available for this pack." title="No subgraph" />
        )}

        {items.length > 0 ? (
          <div className="metric-stack">
            <strong>Contributing evidence</strong>
            {items.map((item) => (
              <div className="metric-row metric-row--stacked" key={item.source_id}>
                <strong>{item.source_type}</strong>
                <span className="metric-row__label">{item.quote}</span>
                <span className="metric-row__label">{item.rationale}</span>
              </div>
            ))}
          </div>
        ) : null}

        {policyCitations.length > 0 ? (
          <div className="metric-stack">
            <strong>Policy citations</strong>
            {policyCitations.map((citation) => (
              <span className="metric-row__label" key={citation.citation_id}>
                <strong>{citation.title}</strong> — {citation.excerpt}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </Card>
  )
}
