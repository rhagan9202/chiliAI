import { Link } from 'react-router-dom'

import type { PolicyItemStatus, PolicySeverity } from '../../api/contracts'
import { usePolicyItems } from '../../api/policy'
import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import { policyItemsForTarget } from './policyTargets'

function toneForSeverity(severity: PolicySeverity) {
  switch (severity) {
    case 'critical':
      return 'danger' as const
    case 'high':
      return 'warning' as const
    case 'medium':
      return 'info' as const
  }
}

function toneForStatus(status: PolicyItemStatus) {
  switch (status) {
    case 'open':
      return 'info' as const
    case 'accepted':
      return 'success' as const
    case 'rejected':
      return 'default' as const
    case 'deferred':
      return 'warning' as const
    case 'escalated':
      return 'network' as const
  }
}

export interface EntityPolicyPanelProps {
  knowledgeBaseId: string | null
  targetKind: 'entity' | 'alert'
  targetRef: string | null
}

export function EntityPolicyPanel({
  knowledgeBaseId,
  targetKind,
  targetRef,
}: EntityPolicyPanelProps) {
  const policyQuery = usePolicyItems(knowledgeBaseId)
  const matches = targetRef
    ? policyItemsForTarget(policyQuery.data?.items ?? [], targetKind, targetRef)
    : []
  if (matches.length === 0) {
    return (
      <EmptyState
        description="No policy items reference this record yet. Review the policy workspace for open determinations."
        title="No policy signals"
      />
    )
  }
  return (
    <div className="metric-stack" data-testid="entity-policy-panel">
      {matches.map((item) => {
        const critical = item.severity === 'critical'
        return (
          <div className={critical ? 'callout--risk' : undefined} key={item.id}>
            {critical ? (
              <span className="flag-label" style={{ color: 'var(--c-red)' }}>
                ⚑ POLICY SIGNAL
              </span>
            ) : null}
            <div className="metric-row metric-row--stacked">
              <strong>{item.title}</strong>
              <div className="alert-row-card__meta">
                <Chip label={item.severity} tone={toneForSeverity(item.severity)} />
                <Chip label={item.status} tone={toneForStatus(item.status)} />
              </div>
              <Link className="metric-row__label" to="/policy">
                Open in policy workspace
              </Link>
            </div>
          </div>
        )
      })}
    </div>
  )
}
