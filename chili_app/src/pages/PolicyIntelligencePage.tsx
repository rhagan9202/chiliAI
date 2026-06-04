import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { useKnowledgeBases } from '../api/knowledgebases'
import { usePolicyItem, usePolicyItems, useTriagePolicyItem } from '../api/policy'
import type { PolicySeverity, PolicyItemStatus, PolicyTriageRequest } from '../api/contracts'
import { showToast } from '../components/common/toastStore'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { FilterBar } from '../components/ui/FilterBar'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

type StatusFilter = 'all' | 'open' | 'accepted' | 'rejected' | 'deferred' | 'escalated'

const STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'open', label: 'Open' },
  { id: 'accepted', label: 'Accepted' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'deferred', label: 'Deferred' },
  { id: 'escalated', label: 'Escalated' },
]

const TRIAGE_ACTIONS: { action: PolicyTriageRequest['action']; label: string; secondary: boolean }[] = [
  { action: 'accept', label: 'Accept', secondary: false },
  { action: 'reject', label: 'Reject', secondary: true },
  { action: 'defer', label: 'Defer', secondary: true },
  { action: 'escalate', label: 'Escalate', secondary: true },
]

export function PolicyIntelligencePage() {
  const [searchParams] = useSearchParams()
  const knowledgeBasesQuery = useKnowledgeBases()
  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const requestedKbId = searchParams.get('kb')
  const knowledgeBaseId = knowledgeBases.some((kb) => kb.id === requestedKbId)
    ? requestedKbId
    : knowledgeBases[0]?.id ?? null

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const itemsQuery = usePolicyItems(knowledgeBaseId, statusFilter === 'all' ? undefined : statusFilter)
  const items = itemsQuery.data?.items ?? []
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const activeItemId = items.some((item) => item.id === selectedItemId)
    ? selectedItemId
    : items[0]?.id ?? null
  const itemQuery = usePolicyItem(knowledgeBaseId, activeItemId)
  const triageMutation = useTriagePolicyItem(knowledgeBaseId)

  if (knowledgeBasesQuery.isLoading) {
    return <LoadingState label="Loading knowledge bases" />
  }

  if (knowledgeBasesQuery.isError) {
    return <ErrorState description="Knowledge base inventory could not be loaded from the backend." />
  }

  if (!knowledgeBaseId) {
    return (
      <section className="page-grid">
        <SectionHeader
          actions={<Chip label="No knowledge base" tone="default" />}
          eyebrow="Policy knowledge graph"
          subtitle="Create or select a knowledge base to review its policy items."
          title="Policy Intelligence"
        />
        <Card>
          <EmptyState
            description="Policy items are scoped to a knowledge base. Select one to view its queue."
            title="No knowledge base selected"
          />
        </Card>
      </section>
    )
  }

  if (itemsQuery.isLoading) {
    return <LoadingState label="Loading policy item queue" />
  }

  if (itemsQuery.isError) {
    return <ErrorState description="Policy intelligence data could not be loaded from the backend." />
  }

  const handleTriage = (action: PolicyTriageRequest['action']) => {
    if (!activeItemId) {
      return
    }
    triageMutation.mutate(
      { itemId: activeItemId, payload: { action } },
      {
        onSuccess: () => showToast('success', `Policy item ${action}ed.`),
        onError: () => showToast('error', 'Could not record the triage decision.'),
      },
    )
  }

  const detail = itemQuery.data
  const disposition = detail?.disposition ?? null

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label={`${itemsQuery.data?.total ?? items.length} items`} tone="info" />}
        eyebrow="Policy knowledge graph"
        subtitle="Configured rule packs generate durable, KB-scoped policy items for analyst triage."
        title="Policy Intelligence"
      />

      <FilterBar
        activeFilterId={statusFilter}
        filters={STATUS_FILTERS}
        onChange={(value) => setStatusFilter(value as StatusFilter)}
      />

      <div className="policy-layout">
        <Card>
          <div className="metric-stack">
            <strong>Item queue</strong>
            {items.map((item) => (
              <button
                className={activeItemId === item.id ? 'page-list-item page-list-item--active' : 'page-list-item'}
                key={item.id}
                onClick={() => setSelectedItemId(item.id)}
                type="button"
              >
                <strong>{item.title}</strong>
                <span className="metric-row__label">Updated {formatTimestamp(item.updated_at)}</span>
                <div className="alert-row-card__meta">
                  <Chip label={item.severity} tone={toneForSeverity(item.severity)} />
                  <Chip label={item.status} tone={toneForStatus(item.status)} />
                </div>
              </button>
            ))}
            {items.length === 0 ? (
              <EmptyState description="No policy items match the current filter." title="Empty queue" />
            ) : null}
          </div>
        </Card>

        <div className="policy-main">
          {itemQuery.isLoading ? (
            <Card>
              <LoadingState label="Loading policy item detail" />
            </Card>
          ) : itemQuery.isError ? (
            <Card>
              <ErrorState description="Policy item detail could not be loaded from the backend." />
            </Card>
          ) : detail ? (
            <Card>
              <div className="metric-stack">
                <div className="metric-row metric-row--stacked">
                  <strong>{detail.item.title}</strong>
                  <span className="metric-row__label">
                    {detail.item.target_kind} · {detail.item.target_ref}
                  </span>
                </div>
                <div className="alert-row-card__meta">
                  <Chip label={detail.item.severity} tone={toneForSeverity(detail.item.severity)} />
                  <Chip label={detail.item.status} tone={toneForStatus(detail.item.status)} />
                  <Chip label={detail.item.rule_id} tone="default" />
                </div>

                <div className="page-actions-inline">
                  {TRIAGE_ACTIONS.map(({ action, label, secondary }) => (
                    <button
                      className={secondary ? 'page-button page-button--secondary' : 'page-button'}
                      disabled={triageMutation.isPending || detail.item.status !== 'open'}
                      key={action}
                      onClick={() => handleTriage(action)}
                      type="button"
                    >
                      {label}
                    </button>
                  ))}
                </div>

                <div className="metric-stack">
                  <strong>Matched fields</strong>
                  {Object.keys(detail.matched_fields).length > 0 ? (
                    Object.entries(detail.matched_fields).map(([field, value]) => (
                      <div className="metric-row" key={field}>
                        <span className="metric-row__label">{field}</span>
                        <strong>{String(value)}</strong>
                      </div>
                    ))
                  ) : (
                    <EmptyState description="No matched fields were recorded." title="No matched fields" />
                  )}
                </div>

                <div className="metric-stack">
                  <strong>Policy citations</strong>
                  {detail.citations.length > 0 ? (
                    detail.citations.map((citation) => (
                      <div className="policy-citation-card" key={citation.citation_id}>
                        <strong>{citation.title}</strong>
                        <span className="metric-row__label">{citation.source_ref}</span>
                        {citation.excerpt ? <p className="page-copy-block">{citation.excerpt}</p> : null}
                      </div>
                    ))
                  ) : (
                    <EmptyState description="No policy citations are attached to this item." title="No citations" />
                  )}
                </div>

                {disposition ? (
                  <div className="metric-stack">
                    <strong>Disposition</strong>
                    <div className="metric-row metric-row--stacked">
                      <strong>{disposition.action} · {disposition.actor}</strong>
                      <span className="metric-row__label">
                        Decided {formatTimestamp(disposition.decided_at)}
                        {disposition.case_id ? ` · case ${disposition.case_id}` : ''}
                      </span>
                      {disposition.note ? <span className="metric-row__label">{disposition.note}</span> : null}
                    </div>
                  </div>
                ) : null}
              </div>
            </Card>
          ) : (
            <EmptyState description="Select a policy item to inspect its detail and triage it." title="No item selected" />
          )}
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
