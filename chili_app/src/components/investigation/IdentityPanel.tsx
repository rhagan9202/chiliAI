import type {
  CanonicalIdentityDetailResponse,
  IdentityLinkResponse,
} from '../../api/contracts'
import { Card } from '../ui/Card'
import { ConfidenceBar } from '../ui/ConfidenceBar'
import { EmptyState } from '../ui/EmptyState'
import { ErrorState } from '../ui/ErrorState'
import { LoadingState } from '../ui/LoadingState'

export interface IdentityPanelProps {
  detail: CanonicalIdentityDetailResponse | null
  isError: boolean
  isLoading: boolean
  sensitiveSourceRefPatterns?: RegExp[]
}

const DEFAULT_SENSITIVE_SOURCE_REF_PATTERNS = [
  /(^|[^a-z0-9])(beneficiary|mbi|hicn|ssn|patient|dob|mrn)([^a-z0-9]|$)/i,
]

function displayText(value: string): string {
  return value.replace(/_/g, ' ')
}

function confidenceScore(link: IdentityLinkResponse): number {
  if (typeof link.score === 'number') {
    return Math.round(link.score * 100)
  }
  return { high: 90, medium: 60, low: 30 }[link.confidence]
}

function sourceRefLabel(ref: string, sensitivePatterns: RegExp[]): string {
  return sensitivePatterns.some((pattern) => pattern.test(ref)) ? 'Restricted ref' : ref
}

function matchReasonLabel(reason: Record<string, unknown>): string | null {
  const field = typeof reason.field === 'string' ? reason.field : null
  const label = typeof reason.reason === 'string' ? reason.reason : null
  if (!field && !label) return null
  return [field, label ? displayText(label) : null].filter(Boolean).join(' · ')
}

function IdentityLinkRow({
  link,
  sensitivePatterns,
}: {
  link: IdentityLinkResponse
  sensitivePatterns: RegExp[]
}) {
  const firstReason = link.match_reasons
    .map((reason) => matchReasonLabel(reason))
    .find((label): label is string => Boolean(label))
  return (
    <div className="metric-row metric-row--stacked">
      <span className="metric-row__label">{link.relationship_type}</span>
      <strong>{link.source_entity_id}</strong>
      <div className="dashboard-panels">
        <div className="metric-row metric-row--stacked">
          <span className="metric-row__label">Confidence</span>
          <strong>{`${link.confidence} confidence`}</strong>
          <ConfidenceBar value={confidenceScore(link)} />
        </div>
        <div className="metric-row metric-row--stacked">
          <span className="metric-row__label">Review</span>
          <strong>{displayText(link.review_state)}</strong>
          <span className="metric-row__label">{link.decision_source}</span>
        </div>
        {firstReason ? (
          <div className="metric-row metric-row--stacked">
            <span className="metric-row__label">Reason</span>
            <strong>{firstReason}</strong>
          </div>
        ) : null}
      </div>
      {link.source_refs.length > 0 ? (
        <div className="page-actions-inline" aria-label="Source references" role="group">
          {link.source_refs.map((ref) => (
            <span className="flag-label" key={ref}>
              {sourceRefLabel(ref, sensitivePatterns)}
            </span>
          ))}
        </div>
      ) : null}
      {link.decision_history.length > 0 ? (
        <div className="metric-stack">
          <span className="metric-row__label">Decision history</span>
          {link.decision_history.map((decision) => (
            <div
              className="metric-row metric-row--stacked"
              key={`${decision.created_at}:${decision.actor_user_id}:${decision.decision}`}
            >
              <strong>{displayText(decision.decision)}</strong>
              <span className="metric-row__label">
                {decision.comment?.trim()
                  ? `${decision.actor_user_id}: ${decision.comment.trim()}`
                  : decision.actor_user_id}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function IdentityPanel({
  detail,
  isError,
  isLoading,
  sensitiveSourceRefPatterns = DEFAULT_SENSITIVE_SOURCE_REF_PATTERNS,
}: IdentityPanelProps) {
  return (
    <Card compact>
      <div aria-label="Identity resolution" className="metric-stack" role="group">
        <div className="metric-row">
          <strong>Identity resolution</strong>
          <span className="metric-row__label">
            {detail ? `${detail.total} linked source ${detail.total === 1 ? 'identity' : 'identities'}` : 'Canonical links'}
          </span>
        </div>
        {isError ? (
          <ErrorState description="Identity links could not be loaded for this entity." />
        ) : isLoading ? (
          <LoadingState label="Loading identity links" />
        ) : detail && detail.links.length > 0 ? (
          detail.links.map((link) => (
            <IdentityLinkRow
              key={link.id}
              link={link}
              sensitivePatterns={sensitiveSourceRefPatterns}
            />
          ))
        ) : (
          <EmptyState
            description="Canonical identity links appear after resolution has run."
            title="No identity links"
          />
        )}
      </div>
    </Card>
  )
}
