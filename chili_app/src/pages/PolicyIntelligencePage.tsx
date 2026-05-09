import { useState } from 'react'

import {
  useCreatePolicyBrief,
  usePolicyGap,
  usePolicyGapCases,
  usePolicyGaps,
} from '../api/policy'
import { ChartFrame } from '../components/charts/ChartFrame'
import { TrendBars } from '../components/charts/TrendBars'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

export function PolicyIntelligencePage() {
  const gapsQuery = usePolicyGaps()
  const [selectedGapId, setSelectedGapId] = useState<string | null>(null)
  const [briefAudience, setBriefAudience] = useState('Operations leadership')
  const [briefObjective, setBriefObjective] = useState('Summarize the policy gap and recommended guidance update.')

  const gaps = gapsQuery.data?.items ?? []
  const activeGapId = gaps.some((gap) => gap.id === selectedGapId) ? selectedGapId : gaps[0]?.id ?? null
  const gapQuery = usePolicyGap(activeGapId)
  const gapCasesQuery = usePolicyGapCases(activeGapId)
  const createBriefMutation = useCreatePolicyBrief()

  if (gapsQuery.isLoading) {
    return <LoadingState label="Loading policy intelligence queue" />
  }

  if (gapsQuery.isError) {
    return <ErrorState description="Policy intelligence data could not be loaded from the backend." />
  }

  if (!gapsQuery.data) {
    return <LoadingState label="Waiting for policy gap queue" />
  }

  if (gaps.length === 0) {
    return (
      <section className="page-grid">
        <SectionHeader
          actions={<Chip label="0 active gaps" tone="info" />}
          eyebrow="Policy knowledge graph"
          subtitle="No policy intelligence gaps are currently available from the backend read model."
          title="Policy Intelligence"
        />
        <EmptyState
          description="Once policy-linked investigation patterns are aggregated into the PKG surface, they will appear here for supervisor review."
          title="No policy gaps detected"
        />
      </section>
    )
  }

  if (gapQuery.isLoading || gapCasesQuery.isLoading) {
    return <LoadingState label="Loading policy gap detail" />
  }

  if (gapQuery.isError || gapCasesQuery.isError) {
    return <ErrorState description="Policy gap detail could not be loaded from the backend." />
  }

  if (!gapQuery.data || !gapCasesQuery.data) {
    return <LoadingState label="Waiting for policy gap detail" />
  }

  const gapDetail = gapQuery.data
  const affectedCases = gapCasesQuery.data.items
  const generatedBrief = createBriefMutation.data

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label={`${gaps.length} active gaps`} tone="info" />}
        eyebrow="Policy knowledge graph"
        subtitle="Phase 7 replaces the placeholder with a live policy gap queue, PKG citations, affected case context, trend evidence, and a backend-generated brief builder."
        title="Policy Intelligence"
      />

      <div className="policy-layout">
        <Card>
          <div className="metric-stack">
            <div className="metric-row">
              <strong>Policy gaps</strong>
              <Chip label={gapDetail.gap.status} tone={toneForGapStatus(gapDetail.gap.status)} />
            </div>

            {gaps.map((gap) => (
              <button
                className={activeGapId === gap.id ? 'page-list-item page-list-item--active' : 'page-list-item'}
                key={gap.id}
                onClick={() => setSelectedGapId(gap.id)}
                type="button"
              >
                <strong>{gap.title}</strong>
                <span className="metric-row__label">Updated {formatTimestamp(gap.updated_at)}</span>
                <div className="alert-row-card__meta">
                  <Chip label={gap.severity} tone={toneForGapSeverity(gap.severity)} />
                  <Chip label={`${gap.affected_case_count} cases`} tone="warning" />
                  <Chip label={`${gap.impacted_entities} entities`} tone="network" />
                </div>
              </button>
            ))}
          </div>
        </Card>

        <div className="policy-main">
          <Card>
            <div className="metric-stack">
              <div className="metric-row metric-row--stacked">
                <strong>{gapDetail.gap.title}</strong>
                <span className="metric-row__label">{gapDetail.summary}</span>
              </div>
              <div className="alert-row-card__meta">
                <Chip label={gapDetail.gap.severity} tone={toneForGapSeverity(gapDetail.gap.severity)} />
                <Chip label={gapDetail.gap.status} tone={toneForGapStatus(gapDetail.gap.status)} />
                <Chip label={`${gapDetail.gap.impacted_entities} impacted entities`} tone="network" />
              </div>
              <div className="policy-copy-grid">
                <div className="policy-copy-block">
                  <strong>Impact</strong>
                  <p className="page-copy-block">{gapDetail.impact_statement}</p>
                </div>
                <div className="policy-copy-block">
                  <strong>Recommended guidance</strong>
                  <p className="page-copy-block">{gapDetail.recommendation}</p>
                </div>
              </div>
            </div>
          </Card>

          <div className="policy-detail-grid">
            <ChartFrame
              eyebrow="Trend evidence"
              footer={<Chip label="Policy signal volume" tone="info" />}
              subtitle="Observed growth in policy-linked review demand across recent reporting windows."
              title="Gap trend"
            >
              <TrendBars color="#7dd3fc" data={gapDetail.trend} />
            </ChartFrame>

            <Card>
              <div className="metric-stack">
                <div className="metric-row">
                  <strong>Policy citations</strong>
                  <Chip label={`${gapDetail.policy_citations.length} references`} tone="default" />
                </div>
                {gapDetail.policy_citations.map((citation) => (
                  <div className="policy-citation-card" key={citation.citation_id}>
                    <strong>{citation.title}</strong>
                    <span className="metric-row__label">{citation.source_document_id}</span>
                    <p className="page-copy-block">{citation.excerpt}</p>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <div className="policy-detail-grid">
            <Card>
              <div className="metric-stack">
                <div className="metric-row">
                  <strong>Affected cases</strong>
                  <Chip label={`${affectedCases.length} cases`} tone="warning" />
                </div>
                {affectedCases.length > 0 ? (
                  affectedCases.map((caseItem) => (
                    <div className="policy-case-card" key={caseItem.id}>
                      <div className="metric-row">
                        <strong>{caseItem.title}</strong>
                        <div className="alert-row-card__meta">
                          <Chip label={caseItem.priority} tone={toneForGapSeverity(caseItem.priority === 'critical' ? 'critical' : caseItem.priority === 'high' ? 'high' : 'medium')} />
                          <Chip label={caseItem.status} tone="info" />
                        </div>
                      </div>
                      <span className="metric-row__label">
                        {caseItem.assignee ? `Assigned to ${caseItem.assignee}` : 'Awaiting assignment'}
                      </span>
                    </div>
                  ))
                ) : (
                  <EmptyState description="No affected cases are linked to this policy gap yet." title="No cases linked" />
                )}
              </div>
            </Card>

            <Card>
              <div className="metric-stack">
                <div className="metric-row">
                  <strong>Policy brief builder</strong>
                  <Chip label="Triage support" tone="info" />
                </div>
                <input
                  className="page-input"
                  onChange={(event) => setBriefAudience(event.target.value)}
                  placeholder="Audience"
                  value={briefAudience}
                />
                <textarea
                  className="page-textarea"
                  onChange={(event) => setBriefObjective(event.target.value)}
                  placeholder="Describe the policy brief objective"
                  value={briefObjective}
                />
                <button
                  className="page-button"
                  disabled={
                    createBriefMutation.isPending ||
                    briefAudience.trim().length === 0 ||
                    briefObjective.trim().length === 0
                  }
                  onClick={() =>
                    createBriefMutation.mutate({
                      gap_id: gapDetail.gap.id,
                      audience: briefAudience.trim(),
                      objective: briefObjective.trim(),
                    })
                  }
                  type="button"
                >
                  {createBriefMutation.isPending ? 'Generating brief…' : 'Generate policy brief'}
                </button>

                {generatedBrief ? (
                  <div className="policy-brief-card">
                    <div className="metric-row metric-row--stacked">
                      <strong>{generatedBrief.title}</strong>
                      <span className="metric-row__label">
                        {generatedBrief.audience} • {formatTimestamp(generatedBrief.created_at)}
                      </span>
                    </div>
                    <p className="page-copy-block">{generatedBrief.narrative}</p>
                    <div className="metric-stack">
                      <strong>Recommendations</strong>
                      {generatedBrief.recommendations.map((recommendation) => (
                        <div className="policy-brief-card__item" key={recommendation}>
                          {recommendation}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <EmptyState
                    description="Generate a brief to package the current policy gap, citations, and recommendations for a supervisor audience."
                    title="No brief generated"
                  />
                )}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </section>
  )
}

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function toneForGapSeverity(severity: 'medium' | 'high' | 'critical') {
  switch (severity) {
    case 'critical':
      return 'danger' as const
    case 'high':
      return 'warning' as const
    case 'medium':
      return 'info' as const
  }
}

function toneForGapStatus(status: 'monitoring' | 'drafting' | 'recommended') {
  switch (status) {
    case 'recommended':
      return 'success' as const
    case 'drafting':
      return 'warning' as const
    case 'monitoring':
      return 'info' as const
  }
}