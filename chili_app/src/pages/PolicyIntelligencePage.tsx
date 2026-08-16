import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { usePolicyItem, usePolicyItems, useTriagePolicyItem } from '../api/policy'
import type { PolicyItemStatus, PolicyTriageRequest } from '../api/contracts'
import { showToast } from '../components/common/toastStore'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { FilterGroup } from '../components/ui/FilterGroup'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import { useActiveKnowledgeBase } from '../hooks/useActiveKnowledgeBase'
import { useUrlSearchDraft } from '../hooks/useUrlSearchDraft'
import { countLabel } from '../utils/countLabel'
import { knowledgeBaseWorkspacePath } from '../utils/knowledgeBaseRoutes'
import {
  EMPTY_POLICY_FILTERS,
  hasActivePolicyFilters,
  parsePolicyFilters,
  serializePolicyFilters,
  summarizePolicyFilters,
  togglePolicyStatus,
  totalFromStatusCounts,
  type PolicyFilterState,
} from '../utils/policyFilters'
import { severityTone } from '../utils/severity'
import './pages.css'

/** Long enough to coalesce a typed word into one request, short enough to feel live. */
const SEARCH_COMMIT_DELAY_MS = 250

const STATUS_OPTIONS: { id: PolicyItemStatus; label: string }[] = [
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
  const {
    activeKnowledgeBaseId: knowledgeBaseId,
    isLoading: knowledgeBasesLoading,
    isError: knowledgeBasesError,
  } = useActiveKnowledgeBase()

  const [searchParams, setSearchParams] = useSearchParams()
  // URL-backed so a filtered queue is shareable and survives a reload (UXA-401).
  // `replace` because a filter is a view state, not a destination: pushing would
  // make the back button walk through every toggle instead of leaving the page.
  const filters = parsePolicyFilters(searchParams)
  const setFilters = (next: PolicyFilterState) => {
    const params = new URLSearchParams(searchParams)
    for (const key of ['status', 'q']) params.delete(key)
    for (const [key, value] of serializePolicyFilters(next)) params.append(key, value)
    setSearchParams(params, { preventScrollReset: true, replace: true })
  }
  // Every committed keystroke is a filtered SQL query, so the URL write waits
  // for a pause in typing; the box itself stays instant.
  const [searchDraft, setSearchDraft] = useUrlSearchDraft(
    filters.search,
    (next) => setFilters({ ...parsePolicyFilters(searchParams), search: next }),
    SEARCH_COMMIT_DELAY_MS,
  )

  const itemsQuery = usePolicyItems(knowledgeBaseId, {
    statuses: filters.statuses,
    search: filters.search,
  })
  const items = itemsQuery.data?.items ?? []
  const statusCounts = itemsQuery.data?.status_counts ?? {}
  const knowledgeBaseTotal = totalFromStatusCounts(statusCounts)
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const activeItemId = items.some((item) => item.id === selectedItemId)
    ? selectedItemId
    : items[0]?.id ?? null
  const itemQuery = usePolicyItem(knowledgeBaseId, activeItemId)
  const triageMutation = useTriagePolicyItem(knowledgeBaseId)

  if (knowledgeBasesLoading) {
    return <LoadingState label="Loading knowledge bases" />
  }

  if (knowledgeBasesError) {
    return <ErrorState description="Your knowledge bases could not be loaded. Try again in a moment." />
  }

  if (!knowledgeBaseId) {
    return (
      <section className="page-grid">
        <SectionHeader
          actions={<Chip label="No knowledge base" tone="default" />}
          eyebrow="Rule findings"
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
    return <ErrorState description="Policy items could not be loaded. Try again in a moment." />
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
        actions={<Chip label={countLabel(knowledgeBaseTotal, 'item')} tone="info" />}
        eyebrow="Rule findings"
        subtitle="Decide what the configured rules found: accept a finding, reject it, defer it, or escalate it to an investigation."
        title="Policy Intelligence"
      />

      <div className="alert-filter-strip">
        <FilterGroup
          label="Status"
          onToggle={(optionId) => setFilters(togglePolicyStatus(filters, optionId))}
          options={STATUS_OPTIONS.map((option) => ({
            ...option,
            count: statusCounts[option.id] ?? 0,
          }))}
          selected={filters.statuses}
        />
        <div className="alert-filter-strip__controls">
          <label className="filter-group__label" htmlFor="policy-search">
            Search
          </label>
          <input
            className="page-input--inline"
            id="policy-search"
            // The API caps `q` at 200 characters; stopping the input there beats
            // letting a long paste come back as a 422.
            maxLength={200}
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder="Item title"
            type="search"
            value={searchDraft}
          />
        </div>
        <div className="alert-filter-strip__summary">
          <span aria-live="polite">
            {summarizePolicyFilters({
              shown: items.length,
              total: knowledgeBaseTotal,
              filters,
            })}
          </span>
          {hasActivePolicyFilters(filters) ? (
            <button
              className="page-button page-button--sm page-button--secondary"
              onClick={() => setFilters(EMPTY_POLICY_FILTERS)}
              type="button"
            >
              Clear filters
            </button>
          ) : null}
        </div>
      </div>

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
                  <Chip label={item.severity} tone={severityTone(item.severity)} />
                  <Chip label={item.status} tone={toneForStatus(item.status)} />
                </div>
              </button>
            ))}
            {items.length === 0 ? (
              // The queue is filtered server-side, so the filter state — not a
              // comparison against a fuller list — is what distinguishes
              // "hidden by a filter" from "nothing here at all" (UXA-305).
              hasActivePolicyFilters(filters) ? (
                <EmptyState
                  action={
                    <button
                      className="page-button page-button--sm"
                      onClick={() => setFilters(EMPTY_POLICY_FILTERS)}
                      type="button"
                    >
                      Clear filters
                    </button>
                  }
                  description={`No policy items match the filters you have set. ${countLabel(knowledgeBaseTotal, 'item')} are in the queue.`}
                  title="No items match these filters"
                />
              ) : (
                <EmptyState
                  action={
                    <Link
                      className="page-button page-button--sm page-button--primary"
                      to={knowledgeBaseWorkspacePath(knowledgeBaseId)}
                    >
                      Add data to this knowledge base
                    </Link>
                  }
                  description="Policy items appear when the configured rules find something in ingested records. Nothing has matched yet."
                  title="No policy items yet"
                />
              )
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
              <ErrorState description="This policy item could not be opened. Try again, or pick another item." />
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
                  <Chip label={detail.item.severity} tone={severityTone(detail.item.severity)} />
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
