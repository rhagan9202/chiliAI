import { useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { useDomainConfig } from '../api/config'
import {
  useCreateKnowledgeBase,
  useDeleteKnowledgeBase,
  useKnowledgeBase,
  useKnowledgeBases,
} from '../api/knowledgebases'
import {
  useCancelScoreRun,
  useReplayScoreRun,
  useScoreRun,
  useScoreRuns,
  useStartScoreRun,
} from '../api/scoreRuns'
import { useWorkflows } from '../api/workflows'
import { KnowledgeBaseSelector } from '../components/ingestion/KnowledgeBaseSelector'
import { isDomainMismatch } from '../components/knowledgebase/domainMismatch'
import { KbDomainBadge } from '../components/knowledgebase/KbDomainBadge'
import { ScoreRunStatusPanel } from '../components/knowledgebase/ScoreRunStatusPanel'
import { RunTimeline } from '../components/ingestion/RunTimeline'
import { ConfirmDialog } from '../components/status/ConfirmDialog'
import { StatusChip } from '../components/status/StatusChip'
import { formatTimestamp } from '../components/status/formatters'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import { AddDataSection } from '../features/kb/add-data/AddDataSection'
import { DataSection } from '../features/kb/data/DataSection'
import { useIngestionDraftStore } from '../stores/ingestionDraftStore'
import { countLabel } from '../utils/countLabel'
import './pages.css'

export function KnowledgeBaseManagerPage() {
  const navigate = useNavigate()
  // Selector subscription only, not a bare `useIngestionDraftStore()`: staging
  // state itself belongs to AddDataSection now, but a deleted knowledge base's
  // draft has nowhere left to submit to, so this page still clears it.
  const clearDraft = useIngestionDraftStore((state) => state.clearDraft)
  const knowledgeBasesQuery = useKnowledgeBases()
  const domainConfigQuery = useDomainConfig()
  // Honor a ?kb= deep-link as the initial selection, matching the convention on
  // AlertFeedPage / PolicyIntelligencePage / InvestigationWorkbenchPage. If the
  // requested KB isn't in the visible list, the auto-select fallback below wins.
  const [searchParams] = useSearchParams()
  const requestedKnowledgeBaseId = searchParams.get('kb')
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<string | null>(
    () => requestedKnowledgeBaseId,
  )
  const [knowledgeBaseName, setKnowledgeBaseName] = useState('')
  const [knowledgeBaseDescription, setKnowledgeBaseDescription] = useState('')
  const [selectedScoreRunId, setActiveScoreRunId] = useState<string | null>(null)
  // This tab just handed a submission to the server (AddDataSection's
  // onSubmitted). It says nothing about history — the run timeline is the
  // record of what happened — only that the handoff succeeded and the run
  // has yet to surface in the poll.
  const [submissionAccepted, setSubmissionAccepted] = useState(false)
  const [showAllDomains, setShowAllDomains] = useState(false)
  // Destructive actions are staged in state and executed from a confirmation
  // dialog: both deletions used to fire on the first click.
  const [confirmingKnowledgeBaseDelete, setConfirmingKnowledgeBaseDelete] = useState(false)
  // The staging form lives in the main column while the inventory that reports
  // "no documents yet" sits in the aside; the empty state's action has to take
  // the analyst back across the page to it (UXA-305).
  const sourceStepRef = useRef<HTMLDivElement | null>(null)

  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const activeDomainName = domainConfigQuery.data?.domain.name ?? null
  // Default scope: KBs stamped with the active domain plus legacy KBs without a
  // domain stamp (isDomainMismatch never flags a null/undefined KB domain).
  const scopedKnowledgeBases = knowledgeBases.filter(
    (item) => !isDomainMismatch(item.domain ?? null, activeDomainName),
  )
  const hiddenDomainCount = knowledgeBases.length - scopedKnowledgeBases.length
  const visibleKnowledgeBases = showAllDomains ? knowledgeBases : scopedKnowledgeBases
  // Auto-select prefers in-scope KBs; an explicit selection is honored only
  // while its KB is visible, so scoping back down can never leave the run
  // timeline or document inventory pointed at an out-of-scope KB.
  const activeKnowledgeBaseId = visibleKnowledgeBases.some(
    (item) => item.id === selectedKnowledgeBaseId,
  )
    ? selectedKnowledgeBaseId
    : scopedKnowledgeBases[0]?.id ?? visibleKnowledgeBases[0]?.id ?? null
  const workflowsQuery = useWorkflows(
    { knowledgeBaseId: activeKnowledgeBaseId ?? undefined },
    { enabled: Boolean(activeKnowledgeBaseId) },
  )
  const knowledgeBaseDetailQuery = useKnowledgeBase(activeKnowledgeBaseId)
  const scoreRunsQuery = useScoreRuns(activeKnowledgeBaseId, { limit: 1 })
  const scoreRuns = scoreRunsQuery.data?.items ?? []
  const activeScoreRunId = selectedScoreRunId ?? scoreRuns[0]?.id ?? null
  const scoreRunQuery = useScoreRun(activeKnowledgeBaseId, activeScoreRunId)
  const workflows = workflowsQuery.data?.items ?? []
  const knowledgeBase = knowledgeBaseDetailQuery.data ?? null
  // The timeline earns its card once there is something to time. Documents are
  // owned by the data section now, so ask the workflow list alone; a knowledge
  // base with documents always has the runs that produced them.
  const runTimelineVisible = workflows.length > 0

  const createKnowledgeBaseMutation = useCreateKnowledgeBase()
  const deleteKnowledgeBaseMutation = useDeleteKnowledgeBase()
  const startScoreRunMutation = useStartScoreRun(activeKnowledgeBaseId)
  const cancelScoreRunMutation = useCancelScoreRun(activeKnowledgeBaseId, activeScoreRunId)
  const replayScoreRunMutation = useReplayScoreRun(activeKnowledgeBaseId, activeScoreRunId)

  if (knowledgeBasesQuery.isLoading || domainConfigQuery.isLoading) {
    return <LoadingState label="Loading knowledge bases" />
  }

  if (knowledgeBasesQuery.isError || domainConfigQuery.isError) {
    return <ErrorState description="Your knowledge bases could not be loaded. Try again in a moment." />
  }

  if (!knowledgeBasesQuery.data || !domainConfigQuery.data) {
    return <LoadingState label="Waiting for knowledge base configuration" />
  }

  if (activeKnowledgeBaseId && knowledgeBaseDetailQuery.isLoading) {
    return <LoadingState label="Loading selected knowledge base" />
  }

  if (knowledgeBaseDetailQuery.isError) {
    return <ErrorState description="This knowledge base could not be opened. Try again, or pick another one." />
  }

  const activeKnowledgeBaseSearch = knowledgeBaseSearch(activeKnowledgeBaseId)
  const scoreRunStartDisabled = !knowledgeBase || knowledgeBase.entity_count === 0
  // A disabled control explains itself in adjacent text, and the explanation
  // has to match the actual blocker — "requires ingested entities" is a lie
  // when the real problem is that no knowledge base is selected.
  const scoreRunStartReason = !activeKnowledgeBaseId
    ? 'Select a knowledge base first.'
    : scoreRunStartDisabled
      ? 'Start requires ingested entities in this knowledge base.'
      : null
  const scoreRunPendingAction = startScoreRunMutation.isPending
    ? 'start'
    : cancelScoreRunMutation.isPending
      ? 'cancel'
      : replayScoreRunMutation.isPending
        ? 'replay'
        : null

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label="Documents + records" tone="info" />}
        eyebrow="Ingestion"
        subtitle="Add documents and structured records to a knowledge base, and check what has already landed in it."
        title="Knowledge Bases"
      />

      <div className="ingestion-studio-layout">
        <div className="ingestion-studio-main">
          <Card>
            <KnowledgeBaseSelector
              activeDomainName={activeDomainName}
              activeKnowledgeBaseId={activeKnowledgeBaseId}
              createDescription={knowledgeBaseDescription}
              createDisabled={createKnowledgeBaseMutation.isPending}
              createName={knowledgeBaseName}
              deleteDisabled={deleteKnowledgeBaseMutation.isPending}
              hiddenDomainCount={hiddenDomainCount}
              knowledgeBases={visibleKnowledgeBases}
              onCreateDescriptionChange={setKnowledgeBaseDescription}
              onCreateNameChange={setKnowledgeBaseName}
              onCreateSubmit={() => {
                createKnowledgeBaseMutation.mutate(
                  {
                    name: knowledgeBaseName.trim(),
                    description: knowledgeBaseDescription.trim(),
                  },
                  {
                    onSuccess: (created) => {
                      setSelectedKnowledgeBaseId(created.id)
                      setActiveScoreRunId(null)
                      setKnowledgeBaseName('')
                      setKnowledgeBaseDescription('')
                    },
                  },
                )
              }}
              onDelete={() => setConfirmingKnowledgeBaseDelete(true)}
              onSelect={(knowledgeBaseId) => {
                setSelectedKnowledgeBaseId(knowledgeBaseId)
                setActiveScoreRunId(null)
              }}
              onToggleShowAllDomains={() => setShowAllDomains((value) => !value)}
              showAllDomains={showAllDomains}
            />
            <ConfirmDialog
              body={
                knowledgeBase
                  ? `Deletes ${countLabel(knowledgeBase.document_count, 'document')}, ${countLabel(
                      knowledgeBase.entity_count,
                      'entity',
                      'entities',
                    )}, ${countLabel(
                      knowledgeBase.relationship_count,
                      'relationship',
                    )}, and every run recorded against it. This cannot be undone.`
                  : 'This cannot be undone.'
              }
              confirmLabel="Delete knowledge base"
              confirmTypedText={knowledgeBase?.name ?? null}
              destructive
              onCancel={() => setConfirmingKnowledgeBaseDelete(false)}
              onConfirm={() => {
                setConfirmingKnowledgeBaseDelete(false)
                if (!activeKnowledgeBaseId) {
                  return
                }
                const deletedId = activeKnowledgeBaseId
                deleteKnowledgeBaseMutation.mutate(deletedId, {
                  onSuccess: () => {
                    // Its draft has nowhere to submit to now.
                    clearDraft(deletedId)
                    setSelectedKnowledgeBaseId(null)
                    setActiveScoreRunId(null)
                  },
                })
              }}
              open={confirmingKnowledgeBaseDelete}
              title="Delete knowledge base"
            />
          </Card>

          {activeKnowledgeBaseId ? (
            // The staging form used to report "no documents yet" via a ref
            // scrolled into view by the empty-inventory action below
            // (UXA-305); AddDataSection owns the form now, so the ref moves
            // to this wrapper instead of the section it used to sit inside.
            <div ref={sourceStepRef}>
              <AddDataSection
                knowledgeBaseId={activeKnowledgeBaseId}
                onSubmitted={() => setSubmissionAccepted(true)}
              />
            </div>
          ) : null}
        </div>

        <aside className="ingestion-studio-context" aria-label="Ingestion context">
          <Card>
            <SelectedKnowledgeBaseSummary
              activeDomainName={activeDomainName}
              knowledgeBase={knowledgeBase}
            />
          </Card>

          <Card>
            <NextActionsPanel
              activeKnowledgeBaseId={activeKnowledgeBaseId}
              submissionAccepted={submissionAccepted}
              hasWorkflows={workflows.length > 0}
              onInvestigateEntities={() => {
                if (!activeKnowledgeBaseSearch) {
                  return
                }
                navigate({ pathname: '/investigation', search: activeKnowledgeBaseSearch })
              }}
              onReviewAlerts={() => {
                if (!activeKnowledgeBaseSearch) {
                  return
                }
                navigate({ pathname: '/alerts', search: activeKnowledgeBaseSearch })
              }}
            />
          </Card>

          {runTimelineVisible ? (
            <Card>
              <RunTimeline workflows={workflows} />
            </Card>
          ) : null}

          <Card>
            <ScoreRunStatusPanel
              detail={scoreRunQuery.data ?? null}
              disabled={!activeKnowledgeBaseId}
              error={scoreRunQuery.isError ? 'Score run status could not be loaded.' : null}
              loading={scoreRunQuery.isLoading}
              onCancel={() => {
                cancelScoreRunMutation.mutate(undefined, {
                  onSuccess: (detail) => setActiveScoreRunId(detail.run.id),
                })
              }}
              onReplay={() => {
                replayScoreRunMutation.mutate(
                  { idempotency_key: `score-replay:${activeScoreRunId ?? 'missing'}` },
                  { onSuccess: (detail) => setActiveScoreRunId(detail.run.id) },
                )
              }}
              onStart={() => {
                if (!activeKnowledgeBaseId || scoreRunStartDisabled) {
                  return
                }
                const currentRun = scoreRunQuery.data?.run
                startScoreRunMutation.mutate(
                  {
                    batch_size: 100,
                    catalog_version: currentRun?.catalog_version ?? 'cms-fraud-features-v1',
                    model_version: currentRun?.model_version ?? 'risk-linear-v1',
                  },
                  { onSuccess: (detail) => setActiveScoreRunId(detail.run.id) },
                )
              }}
              pendingAction={scoreRunPendingAction}
              startDisabled={scoreRunStartDisabled}
              startReason={scoreRunStartReason}
            />
          </Card>

          {activeKnowledgeBaseId ? (
            <DataSection
              knowledgeBaseId={activeKnowledgeBaseId}
              onStageSource={() => {
                const section = sourceStepRef.current
                if (section && typeof section.scrollIntoView === 'function') {
                  section.scrollIntoView({ behavior: 'smooth', block: 'start' })
                }
              }}
            />
          ) : null}
        </aside>
      </div>
    </section>
  )
}

function knowledgeBaseSearch(knowledgeBaseId: string | null): string | null {
  return knowledgeBaseId ? `kb=${encodeURIComponent(knowledgeBaseId)}` : null
}

function NextActionsPanel({
  activeKnowledgeBaseId,
  hasWorkflows,
  submissionAccepted,
  onInvestigateEntities,
  onReviewAlerts,
}: {
  activeKnowledgeBaseId: string | null
  hasWorkflows: boolean
  /** This tab's submission was accepted and its run has yet to appear. */
  submissionAccepted: boolean
  onInvestigateEntities: () => void
  onReviewAlerts: () => void
}) {
  const disabled = !activeKnowledgeBaseId
  const message = hasWorkflows
    ? 'Runs are updating for this knowledge base.'
    : submissionAccepted
      ? 'Submission accepted. Watch for queued or running workflow updates.'
      : 'Submit documents or records to unlock the handoff path.'

  return (
    <section className="ingestion-next-actions" aria-labelledby="ingestion-next-actions-title">
      <div className="metric-row metric-row--stacked">
        <strong id="ingestion-next-actions-title">Next actions</strong>
        <p className="page-copy-block">{message}</p>
      </div>

      <div className="ingestion-next-actions__buttons">
        <button
          className="page-button page-button--secondary"
          disabled={disabled}
          onClick={onInvestigateEntities}
          type="button"
        >
          Investigate entities
        </button>
        <button
          className="page-button page-button--secondary"
          disabled={disabled}
          onClick={onReviewAlerts}
          type="button"
        >
          Review alerts
        </button>
      </div>
    </section>
  )
}

function SelectedKnowledgeBaseSummary({
  activeDomainName,
  knowledgeBase,
}: {
  activeDomainName: string | null
  knowledgeBase: NonNullable<ReturnType<typeof useKnowledgeBase>['data']> | null
}) {
  if (!knowledgeBase) {
    return (
      <EmptyState
        description="Create or select a knowledge base before submitting ingestion runs."
        title="No knowledge base selected"
      />
    )
  }

  const kbDomain = knowledgeBase.domain ?? null
  const hasDomainMismatch = isDomainMismatch(kbDomain, activeDomainName)

  return (
    <section className="ingestion-studio-summary" aria-labelledby="selected-kb-title">
      <div className="metric-row">
        <div>
          <strong id="selected-kb-title">{knowledgeBase.name}</strong>
          <p className="page-copy-block">{knowledgeBase.description}</p>
        </div>
        <StatusChip kind="knowledge-base" status={knowledgeBase.status} />
        <KbDomainBadge activeDomainName={activeDomainName} kbDomain={kbDomain} />
      </div>

      {hasDomainMismatch ? (
        <p className="page-copy-block" data-testid="kb-domain-mismatch-note" role="status">
          This knowledge base was created under the &quot;{kbDomain}&quot; domain, but
          &quot;{activeDomainName}&quot; is now active. Its entities and relationships may not
          match the active domain&apos;s configuration. All actions remain available.
        </p>
      ) : null}

      <div className="knowledge-base-stats">
        <div className="knowledge-base-stat">
          <span className="metric-row__label">Documents</span>
          <strong>{knowledgeBase.document_count}</strong>
        </div>
        <div className="knowledge-base-stat">
          <span className="metric-row__label">Entities</span>
          <strong>{knowledgeBase.entity_count}</strong>
        </div>
        <div className="knowledge-base-stat">
          <span className="metric-row__label">Relationships</span>
          <strong>{knowledgeBase.relationship_count}</strong>
        </div>
        <div className="knowledge-base-stat">
          <span className="metric-row__label">Created</span>
          <strong>{formatTimestamp(knowledgeBase.created_at)}</strong>
        </div>
      </div>
    </section>
  )
}
