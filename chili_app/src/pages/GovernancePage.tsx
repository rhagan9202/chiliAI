import { useDomainConfig } from '../api/config'
import type {
  GovernanceEvalRunResponse,
  GovernancePendingApprovalResponse,
  GovernanceReleaseBlockerResponse,
  GovernanceVersionSummaryResponse,
} from '../api/contracts'
import { useGovernanceReport } from '../api/governance'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import { StatusPill } from '../components/ui/StatusPill'
import type { StatusPillTone } from '../components/ui/statusPill'
import { useActiveKnowledgeBase } from '../hooks/useActiveKnowledgeBase'
import './pages.css'

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return 'Not recorded'
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function readinessLabel(releaseReady: boolean) {
  return releaseReady ? 'ready' : 'blocked'
}

function readinessTone(releaseReady: boolean): StatusPillTone {
  return releaseReady ? 'success' : 'danger'
}

function countTone(count: number, positiveTone: StatusPillTone = 'info'): StatusPillTone {
  return count > 0 ? positiveTone : 'default'
}

function componentKindLabel(
  value:
    | GovernanceVersionSummaryResponse['component_kind']
    | GovernanceEvalRunResponse['artifact_kind'],
) {
  if (value === 'workflow_definition') {
    return 'Workflow definition'
  }
  return value.charAt(0).toUpperCase() + value.slice(1).replaceAll('_', ' ')
}

function formatDelta(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(3)}`
}

function evalStatusTone(status: GovernanceEvalRunResponse['status']): StatusPillTone {
  if (status === 'approved') {
    return 'success'
  }
  if (status === 'rejected') {
    return 'danger'
  }
  return 'warning'
}

function VersionRow({ version }: { version: GovernanceVersionSummaryResponse }) {
  return (
    <div className="dashboard-summary-row">
      <span>
        <strong>{version.component_id}</strong>
        <span className="metric-row__label">
          {componentKindLabel(version.component_kind)} {version.version}
        </span>
      </span>
      <span className="page-actions-inline">
        <StatusPill compact context="Version status" label={version.status} tone="success" />
        <StatusPill compact context="Version source" label={version.source} tone="info" />
      </span>
      <span className="metric-row__label">
        Approved {formatDateTime(version.approved_at)} by {version.approved_by ?? 'unknown'}
      </span>
    </div>
  )
}

function PendingApprovalRow({
  approval,
}: {
  approval: GovernancePendingApprovalResponse
}) {
  return (
    <div className="dashboard-summary-row">
      <span>
        <strong>{approval.resource_id}</strong>
        <span className="metric-row__label">
          {approval.approval_kind} {approval.version}
        </span>
      </span>
      <StatusPill compact context="Approval status" label={approval.status} tone="warning" />
      <span className="metric-row__label">
        Requested by {approval.requested_by} - Updated {formatDateTime(approval.updated_at)}
      </span>
    </div>
  )
}

function BlockerRow({ blocker }: { blocker: GovernanceReleaseBlockerResponse }) {
  return (
    <div className="dashboard-summary-row">
      <span>
        <strong>{blocker.code}</strong>
        <span className="metric-row__label">{blocker.message}</span>
      </span>
      <StatusPill
        compact
        context="Blocker severity"
        label={blocker.severity}
        tone={blocker.severity === 'blocking' ? 'danger' : 'warning'}
      />
    </div>
  )
}

function EvalRunRow({ run }: { run: GovernanceEvalRunResponse }) {
  return (
    <div className="dashboard-summary-row">
      <span>
        <strong>{run.artifact_id}</strong>
        <span className="metric-row__label">{componentKindLabel(run.artifact_kind)}</span>
        <span className="metric-row__label">
          {run.artifact_version} vs {run.baseline_version}
        </span>
      </span>
      <span className="page-actions-inline">
        <StatusPill
          compact
          context="Eval status"
          label={run.status}
          tone={evalStatusTone(run.status)}
        />
        <StatusPill
          compact
          context="Failed eval metrics"
          label={String(run.drift_summary.failed_metric_count)}
          tone={countTone(run.drift_summary.failed_metric_count, 'danger')}
        />
      </span>
      <span className="metric-row__label">
        Dataset {run.dataset_id} - Max drift{' '}
        <strong>{formatDelta(run.drift_summary.max_abs_delta)}</strong>
      </span>
      {run.metrics.map((metric) => (
        <span className="metric-row__label" key={metric.name}>
          <strong>{metric.name}</strong>
          {' '}
          <strong>{formatDelta(metric.delta)}</strong> / {metric.passed ? 'passed' : 'failed'}
        </span>
      ))}
      <span className="metric-row__label">
        Approval {run.approval ? `${run.approval.decision} by ${run.approval.decided_by}` : 'pending'}
      </span>
    </div>
  )
}

export function GovernancePage() {
  const domainConfigQuery = useDomainConfig()
  const activeKnowledgeBase = useActiveKnowledgeBase()
  const governanceQuery = useGovernanceReport(activeKnowledgeBase.activeKnowledgeBaseId)
  const report = governanceQuery.data

  if (activeKnowledgeBase.isLoading) {
    return <LoadingState label="Loading knowledge bases" />
  }

  if (activeKnowledgeBase.isError) {
    return (
      <ErrorState
        title="Knowledge bases could not be loaded"
        description="Governance requires an active knowledge base before release checks can run."
      />
    )
  }

  if (!activeKnowledgeBase.activeKnowledgeBaseId) {
    return (
      <div className="page-grid">
        <SectionHeader
          eyebrow="SAFE-CMS-020"
          title="Governance"
          subtitle="Release evidence, approvals, and feedback checks for the active knowledge base."
        />
        <Card>
          <EmptyState
            title="No knowledge base selected"
            description="Create or select a knowledge base before reviewing governance readiness."
          />
        </Card>
      </div>
    )
  }

  if (governanceQuery.isLoading) {
    return <LoadingState label="Loading governance report" />
  }

  if (governanceQuery.isError || !report) {
    return (
      <ErrorState
        title="Governance report could not be loaded"
        description="The release governance service did not return a report for the selected knowledge base."
      />
    )
  }

  const pendingCount = report.pending_approvals.length
  const challengedCount = report.feedback_trends.challenged_reviews
  const evalRuns = report.eval_runs ?? []
  const domainName = report.domain_name || domainConfigQuery.data?.domain.name || 'domain'

  return (
    <div className="page-grid">
      <SectionHeader
        eyebrow="SAFE-CMS-020"
        title="Governance"
        subtitle={`Release evidence for ${domainName}, generated ${formatDateTime(report.generated_at)}.`}
        actions={
          <StatusPill
            context="Release readiness"
            label={readinessLabel(report.release_ready)}
            tone={readinessTone(report.release_ready)}
          />
        }
      />

      <div className="dashboard-kpis">
        <Card compact>
          <div className="metric-row">
            <span className="metric-row__label">Readiness</span>
            <StatusPill
              context="Readiness summary"
              label={readinessLabel(report.release_ready)}
              tone={readinessTone(report.release_ready)}
            />
          </div>
        </Card>
        <Card compact>
          <div className="metric-row">
            <span className="metric-row__label">Published</span>
            <StatusPill
              context="Published versions"
              label={String(report.production_versions.length)}
              tone={countTone(report.production_versions.length)}
            />
          </div>
        </Card>
        <Card compact>
          <div className="metric-row">
            <span className="metric-row__label">Approvals</span>
            <StatusPill
              context="Pending approvals"
              label={String(pendingCount)}
              tone={countTone(pendingCount, 'warning')}
            />
          </div>
        </Card>
        <Card compact>
          <div className="metric-row">
            <span className="metric-row__label">Feedback</span>
            <StatusPill
              context="Challenged explanations"
              label={String(challengedCount)}
              tone={countTone(challengedCount, 'warning')}
            />
          </div>
        </Card>
        <Card compact>
          <div className="metric-row">
            <span className="metric-row__label">Evals</span>
            <StatusPill
              context="Evaluation runs"
              label={String(evalRuns.length)}
              tone={countTone(evalRuns.length)}
            />
          </div>
        </Card>
      </div>

      <div className="dashboard-panels">
        <section aria-label="Production versions" role="region">
          <Card>
            <div className="metric-stack">
              <div className="metric-row">
                <strong>Production versions</strong>
                <StatusPill
                  compact
                  context="Production version count"
                  label={String(report.production_versions.length)}
                  tone={countTone(report.production_versions.length)}
                />
              </div>
              {report.production_versions.length > 0 ? (
                report.production_versions.map((version) => (
                  <VersionRow
                    key={`${version.component_kind}:${version.component_id}:${version.version}`}
                    version={version}
                  />
                ))
              ) : (
                <EmptyState
                  title="No published versions"
                  description="Publish playbooks and approve workflow definitions before release."
                />
              )}
            </div>
          </Card>
        </section>

        <section aria-label="Pending approvals" role="region">
          <Card>
            <div className="metric-stack">
              <div className="metric-row">
                <strong>Pending approvals</strong>
                <StatusPill
                  compact
                  context="Pending approval count"
                  label={String(pendingCount)}
                  tone={countTone(pendingCount, 'warning')}
                />
              </div>
              {pendingCount > 0 ? (
                report.pending_approvals.map((approval) => (
                  <PendingApprovalRow
                    key={`${approval.approval_kind}:${approval.resource_id}:${approval.version}`}
                    approval={approval}
                  />
                ))
              ) : (
                <EmptyState
                  title="No pending approvals"
                  description="All tracked governance artifacts are approved or published."
                />
              )}
            </div>
          </Card>
        </section>

        <section aria-label="Release blockers" role="region">
          <Card>
            <div className="metric-stack">
              <div className="metric-row">
                <strong>Release blockers</strong>
                <StatusPill
                  compact
                  context="Release blockers"
                  label={String(report.release_blockers.length)}
                  tone={countTone(report.release_blockers.length, 'danger')}
                />
              </div>
              {report.release_blockers.length > 0 ? (
                report.release_blockers.map((blocker) => (
                  <BlockerRow key={`${blocker.code}:${blocker.resource_id}`} blocker={blocker} />
                ))
              ) : (
                <EmptyState
                  title="No release blockers"
                  description="The active knowledge base has no blocking governance issues."
                />
              )}
            </div>
          </Card>
        </section>

        <section aria-label="Evaluation runs" role="region">
          <Card>
            <div className="metric-stack">
              <div className="metric-row">
                <strong>Evaluation runs</strong>
                <StatusPill
                  compact
                  context="Evaluation run count"
                  label={String(evalRuns.length)}
                  tone={countTone(evalRuns.length)}
                />
              </div>
              {evalRuns.length > 0 ? (
                evalRuns.map((run) => <EvalRunRow key={run.run_id} run={run} />)
              ) : (
                <EmptyState
                  title="No evaluation runs"
                  description="Record candidate-vs-baseline evaluations before release promotion."
                />
              )}
            </div>
          </Card>
        </section>
      </div>

      <Card>
        <div className="metric-stack">
          <div className="metric-row">
            <strong>Feedback trends</strong>
            <StatusPill
              compact
              context="Reviewed explanations"
              label={String(report.feedback_trends.total_reviews)}
              tone={countTone(report.feedback_trends.total_reviews)}
            />
          </div>
          <div className="dashboard-kpis">
            <div className="metric-row">
              <span className="metric-row__label">Approved reviews</span>
              <strong>{report.feedback_trends.approved_reviews}</strong>
            </div>
            <div className="metric-row">
              <span className="metric-row__label">Challenged reviews</span>
              <strong>{challengedCount}</strong>
            </div>
            {Object.entries(report.feedback_trends.state_counts).map(([state, count]) => (
              <div className="metric-row" key={state}>
                <span className="metric-row__label">{state}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  )
}
