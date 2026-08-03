import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router'

import type {
  EvidencePackResponse,
  ExplanationReviewCreateRequest,
  ExplanationReviewResponse,
} from '../../api/contracts'
import {
  useCreateEvidencePackReview,
  useEvidencePackReviews,
} from '../../api/explanationReviews'
import { resolveEvidenceCitationTarget } from '../../lib/citationTargets'
import type { Entity, SubgraphResult } from '../../types/api'
import { absoluteTime, relativeAge } from '../../utils/relativeTime'
import { AttributionBars } from '../charts/AttributionBars'
import { Card } from '../ui/Card'
import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import { GraphCanvas } from './GraphCanvas'

export interface EvidencePackViewerProps {
  pack: EvidencePackResponse
  knowledgeBaseId?: string | null
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

type EvidenceProvenanceReference = NonNullable<EvidencePackResponse['provenance']>[number]
type ExplanationReviewState = ExplanationReviewCreateRequest['state']
type ExplanationReviewReason = NonNullable<ExplanationReviewCreateRequest['reasons']>[number]
type ReviewTarget = ExplanationReviewCreateRequest['target']

const PROVENANCE_METADATA_PREVIEW_LIMIT = 4
const PROVENANCE_METADATA_VALUE_MAX_CHARS = 120
const NEGATIVE_REVIEW_STATES = new Set<ExplanationReviewState>([
  'incomplete',
  'misleading',
  'unsupported',
  'rejected',
  'regeneration_requested',
])
const REVIEW_STATES: Array<{ value: ExplanationReviewState; label: string }> = [
  { value: 'useful', label: 'Useful' },
  { value: 'approved', label: 'Approved' },
  { value: 'incomplete', label: 'Incomplete' },
  { value: 'misleading', label: 'Misleading' },
  { value: 'unsupported', label: 'Unsupported' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'regeneration_requested', label: 'Regeneration requested' },
]
const REVIEW_REASONS: Array<{ value: ExplanationReviewReason; label: string }> = [
  { value: 'missing_source', label: 'Missing source' },
  { value: 'wrong_peer_group', label: 'Wrong peer group' },
  { value: 'stale_data', label: 'Stale data' },
  { value: 'unsupported_claim', label: 'Unsupported claim' },
  { value: 'contradicts_evidence', label: 'Contradicts evidence' },
  { value: 'unclear_rationale', label: 'Unclear rationale' },
  { value: 'other', label: 'Other' },
]

/** `peer_deviation` -> `Peer deviation`: score keys are data, not copy. */
function humanizeScoreName(name: string): string {
  const words = name.replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

function humanizeReferenceType(name: string): string {
  return name.replace(/[_-]+/g, ' ').trim()
}

function truncateMetadataValue(value: string): string {
  if (value.length <= PROVENANCE_METADATA_VALUE_MAX_CHARS) return value
  return `${value.slice(0, PROVENANCE_METADATA_VALUE_MAX_CHARS - 3)}...`
}

function stringifyMetadataValue(value: unknown): string {
  if (value === null || value === undefined) return 'null'
  if (Array.isArray(value)) return value.map(stringifyMetadataValue).join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function formatMetadataValue(value: unknown): string {
  return truncateMetadataValue(stringifyMetadataValue(value))
}

function labelize(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function provenanceLabel(reference: EvidenceProvenanceReference): string {
  return reference.label || reference.reference_id
}

function reviewForTarget(
  reviews: ExplanationReviewResponse[],
  target: ReviewTarget,
): ExplanationReviewResponse | null {
  return reviews.find(
    (review) =>
      review.target.target_type === target.target_type
      && review.target.target_id === target.target_id,
  ) ?? null
}

function ExplanationReviewControl({
  currentReview,
  disabled,
  evidencePackId,
  knowledgeBaseId,
  label,
  submitLabel,
  target,
}: {
  currentReview: ExplanationReviewResponse | null
  disabled: boolean
  evidencePackId: string
  knowledgeBaseId: string | null
  label: string
  submitLabel: string
  target: ReviewTarget
}) {
  const createReview = useCreateEvidencePackReview()
  const [state, setState] = useState<ExplanationReviewState>(currentReview?.state ?? 'useful')
  const [reason, setReason] = useState<ExplanationReviewReason | ''>(
    currentReview?.reasons?.[0] ?? '',
  )
  const [comment, setComment] = useState(currentReview?.comment ?? '')
  const [error, setError] = useState<string | null>(null)
  const requiresReason = NEGATIVE_REVIEW_STATES.has(state)
  const controlDisabled = disabled || !knowledgeBaseId || createReview.isPending

  useEffect(() => {
    if (!currentReview) return
    setState(currentReview.state)
    setReason(currentReview.reasons?.[0] ?? '')
    setComment(currentReview.comment ?? '')
    setError(null)
  }, [
    currentReview?.id,
    currentReview?.state,
    currentReview?.comment,
    currentReview?.reasons,
  ])

  const submitReview = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!knowledgeBaseId) return
    if (requiresReason && !reason) {
      setError('Select at least one reason.')
      return
    }
    setError(null)
    createReview.mutate({
      evidencePackId,
      knowledgeBaseId,
      payload: {
        comment: comment.trim() || null,
        reasons: reason ? [reason] : [],
        state,
        target,
      },
    })
  }

  return (
    <form
      aria-label={label}
      className="metric-row metric-row--stacked"
      onSubmit={submitReview}
      role="group"
    >
      <div className="metric-row">
        <strong>{label}</strong>
        <span className="flag-label">
          {currentReview ? labelize(currentReview.state) : 'Unreviewed'}
        </span>
      </div>
      <label className="metric-row__label">
        {label} state
        <select
          className="page-input page-input--inline"
          disabled={controlDisabled}
          onChange={(event) => {
            setState(event.target.value as ExplanationReviewState)
            setError(null)
          }}
          value={state}
        >
          {REVIEW_STATES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      {requiresReason ? (
        <label className="metric-row__label">
          {label} reason
          <select
            className="page-input page-input--inline"
            disabled={controlDisabled}
            onChange={(event) => {
              setReason(event.target.value as ExplanationReviewReason | '')
              setError(null)
            }}
            value={reason}
          >
            <option value="">Select reason</option>
            {REVIEW_REASONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <label className="metric-row__label">
        {label} comment
        <input
          className="page-input"
          disabled={controlDisabled}
          maxLength={1000}
          onChange={(event) => setComment(event.target.value)}
          type="text"
          value={comment}
        />
      </label>
      {error ? <span className="metric-row__label" role="alert">{error}</span> : null}
      <button
        className="page-button page-button--sm page-button--secondary"
        disabled={controlDisabled}
        type="submit"
      >
        {submitLabel}
      </button>
    </form>
  )
}

function ProvenancePanel({
  knowledgeBaseId,
  references,
}: {
  knowledgeBaseId: string | null
  references: EvidenceProvenanceReference[]
}) {
  if (references.length === 0) {
    return null
  }

  return (
    <div className="metric-stack evidence-pack__provenance" data-testid="evidence-provenance">
      <div className="metric-row">
        <strong>Provenance</strong>
        <span className="alert-row-card__age">
          {references.length} {references.length === 1 ? 'reference' : 'references'}
        </span>
      </div>
      <div className="alert-row-card__meta">
        {references.slice(0, 6).map((reference) => (
          <Chip
            key={`${reference.reference_type}:${reference.reference_id}`}
            label={humanizeReferenceType(reference.reference_type)}
            title={provenanceLabel(reference)}
            tone="default"
          />
        ))}
      </div>
      <div className="evidence-pack__provenance-list">
        {references.map((reference) => {
          const label = provenanceLabel(reference)
          const target = resolveEvidenceCitationTarget({ knowledgeBaseId, reference })
          const metadataEntries = Object.entries(reference.metadata ?? {})
          const previewMetadata = metadataEntries.slice(0, PROVENANCE_METADATA_PREVIEW_LIMIT)
          const hiddenMetadataCount = metadataEntries.length - previewMetadata.length
          return (
            <details
              className="config-count evidence-pack__provenance-item"
              key={`${reference.reference_type}:${reference.reference_id}`}
            >
              <summary className="config-count__summary">
                <span>
                  <strong>{label}</strong>
                  <span className="metric-row__label">
                    {humanizeReferenceType(reference.reference_type)} · {reference.reference_id}
                  </span>
                </span>
                {reference.confidence === null || reference.confidence === undefined ? null : (
                  <span className="flag-label">
                    Confidence {(reference.confidence * 100).toFixed(0)}%
                  </span>
                )}
              </summary>
              <div className="config-count__items evidence-pack__provenance-detail">
                {target.kind === 'link' ? (
                  <Link
                    aria-label={`Open citation source ${target.label}`}
                    className="evidence-pack__citation-link"
                    title={target.preview}
                    to={target.to}
                  >
                    Open source
                  </Link>
                ) : (
                  <span className="metric-row__label">
                    <strong>Unsupported</strong> {target.reason}
                  </span>
                )}
                {reference.route_target ? (
                  <span className="evidence-pack__route-target">
                    <strong>route_target</strong> {reference.route_target}
                  </span>
                ) : null}
                {reference.source_system ? (
                  <span>
                    <strong>source_system</strong> {reference.source_system}
                  </span>
                ) : null}
                {reference.source_version ? (
                  <span>
                    <strong>source_version</strong> {reference.source_version}
                  </span>
                ) : null}
                {reference.transformation_version ? (
                  <span>
                    <strong>transformation_version</strong> {reference.transformation_version}
                  </span>
                ) : null}
                {previewMetadata.map(([key, value]) => (
                  <span key={key}>
                    <strong>{key}</strong> {formatMetadataValue(value)}
                  </span>
                ))}
                {hiddenMetadataCount > 0 ? (
                  <span className="metric-row__label">
                    {hiddenMetadataCount} more metadata {hiddenMetadataCount === 1 ? 'field' : 'fields'}
                  </span>
                ) : null}
              </div>
            </details>
          )
        })}
      </div>
    </div>
  )
}

/**
 * Render a persisted evidence pack (BL-006): reasoning, contributing items, a
 * metric snapshot (scores + confidence), policy citations, and the explanatory
 * subgraph via {@link GraphCanvas}. The pack stores node ids only, so the
 * subgraph is resolved by filtering the supplied neighborhood to those ids.
 */
export function EvidencePackViewer({
  pack,
  knowledgeBaseId = null,
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
  const provenance = pack.provenance ?? []
  const reviewsQuery = useEvidencePackReviews(pack.id, knowledgeBaseId)
  const reviews = reviewsQuery.data?.items ?? []
  const canReview = Boolean(knowledgeBaseId)

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
          <ExplanationReviewControl
            currentReview={reviewForTarget(reviews, {
              target_type: 'narrative',
              target_id: 'narrative',
            })}
            disabled={!canReview}
            evidencePackId={pack.id}
            knowledgeBaseId={knowledgeBaseId}
            label="Narrative review"
            submitLabel="Save narrative review"
            target={{ target_type: 'narrative', target_id: 'narrative' }}
          />
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

        {attribution.length > 0 ? (
          <div className="metric-stack">
            {attribution.map((item) => {
              const target: ReviewTarget = {
                target_type: 'feature_attribution',
                target_id: item.feature_name,
              }
              return (
                <ExplanationReviewControl
                  currentReview={reviewForTarget(reviews, target)}
                  disabled={!canReview}
                  evidencePackId={pack.id}
                  key={item.feature_name}
                  knowledgeBaseId={knowledgeBaseId}
                  label={`Feature ${item.feature_name} review`}
                  submitLabel={`Save feature ${item.feature_name} review`}
                  target={target}
                />
              )
            })}
          </div>
        ) : null}

        <ProvenancePanel knowledgeBaseId={knowledgeBaseId} references={provenance} />

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
