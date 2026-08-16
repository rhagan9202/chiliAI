import { useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { useDomainConfig } from '../api/config'
import {
  useCreateKnowledgeBase,
  useDeleteKnowledgeBase,
  useDeleteKnowledgeBaseDocument,
  useKnowledgeBase,
  useKnowledgeBaseDocumentPreview,
  useKnowledgeBaseDocuments,
  useKnowledgeBases,
  useUploadKnowledgeBaseDocuments,
} from '../api/knowledgebases'
import { usePushRecords, useUploadRecordFile } from '../api/records'
import {
  useCancelScoreRun,
  useReplayScoreRun,
  useScoreRun,
  useScoreRuns,
  useStartScoreRun,
} from '../api/scoreRuns'
import type {
  KnowledgeBaseDocumentListResponse,
  KnowledgeBaseDocumentPreviewResponse,
  RecordIngestReceipt,
} from '../api/contracts'
import { useWorkflows } from '../api/workflows'
import { DocumentSourcePanel } from '../components/ingestion/DocumentSourcePanel'
import { KnowledgeBaseSelector } from '../components/ingestion/KnowledgeBaseSelector'
import { isDomainMismatch } from '../components/knowledgebase/domainMismatch'
import { KbDomainBadge } from '../components/knowledgebase/KbDomainBadge'
import { ScoreRunStatusPanel } from '../components/knowledgebase/ScoreRunStatusPanel'
import { RecordsSourcePanel } from '../components/ingestion/RecordsSourcePanel'
import { RecordsPreviewTable } from '../components/ingestion/RecordsPreviewTable'
import { RunTimeline } from '../components/ingestion/RunTimeline'
import { SourceTypeStep } from '../components/ingestion/SourceTypeStep'
import { SubmitPanel } from '../components/ingestion/SubmitPanel'
import { UploadProgress } from '../components/ingestion/UploadProgress'
import type { UploadStatus } from '../components/ingestion/UploadProgress'
import { ValidationPanel } from '../components/ingestion/ValidationPanel'
import { showToast } from '../components/common/toastStore'
import { ConfirmDialog } from '../components/status/ConfirmDialog'
import { StatusChip } from '../components/status/StatusChip'
import { statusToken } from '../components/status/statusTokens'
import { formatFileSize, formatTimestamp } from '../components/status/formatters'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import {
  validateDocumentFiles,
  validateIngestionPrerequisites,
  validateRecordFile,
  validateRecordRows,
} from '../lib/ingestion/validateIngestion'
import { apiErrorMessage } from '../lib/apiClient'
import type { ValidationIssue } from '../lib/ingestion/types'
import { useIngestionDraft, useIngestionDraftStore } from '../stores/ingestionDraftStore'
import type { IngestionDraft } from '../stores/ingestionDraftStore'
import { countLabel } from '../utils/countLabel'
import './pages.css'

export function KnowledgeBaseManagerPage() {
  const navigate = useNavigate()
  // Selector subscriptions only: a bare `useIngestionDraftStore()` re-renders
  // the entire page on every keystroke landing in any draft.
  const updateDraft = useIngestionDraftStore((state) => state.updateDraft)
  const clearDraft = useIngestionDraftStore((state) => state.clearDraft)
  const knowledgeBasesQuery = useKnowledgeBases()
  const domainConfigQuery = useDomainConfig()
  // Honor a ?kb= deep-link as the initial selection, matching the convention on
  // AlertFeedPage / PolicyIntelligencePage / InvestigationWorkbenchPage. If the
  // requested KB isn't in the visible list, the auto-select fallback below wins.
  const [searchParams] = useSearchParams()
  const requestedKnowledgeBaseId = searchParams.get('kb')
  const requestedDocumentId = searchParams.get('document')
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<string | null>(
    () => requestedKnowledgeBaseId,
  )
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(
    () => requestedDocumentId,
  )
  const [knowledgeBaseName, setKnowledgeBaseName] = useState('')
  const [knowledgeBaseDescription, setKnowledgeBaseDescription] = useState('')
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle')
  const [uploadPercent, setUploadPercent] = useState(0)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [selectedScoreRunId, setActiveScoreRunId] = useState<string | null>(null)
  // Holds the last upload invocation so the Retry button can re-run it verbatim.
  const [retryUpload, setRetryUpload] = useState<(() => void) | null>(null)
  const [showAllDomains, setShowAllDomains] = useState(false)
  const [documentStatusFilter, setDocumentStatusFilter] = useState('all')
  // Destructive actions are staged in state and executed from a confirmation
  // dialog: both deletions used to fire on the first click.
  const [confirmingKnowledgeBaseDelete, setConfirmingKnowledgeBaseDelete] = useState(false)
  const [confirmingDocumentDeleteId, setConfirmingDocumentDeleteId] = useState<string | null>(
    null,
  )
  // The staging form lives in the main column while the inventory that reports
  // "no documents yet" sits in the aside; the empty state's action has to take
  // the analyst back across the page to it (UXA-305).
  const sourceStepRef = useRef<HTMLElement | null>(null)

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
  // Staging work belongs to the knowledge base it was staged for. Switching
  // knowledge base switches drafts; it never carries one across.
  const draft = useIngestionDraft(activeKnowledgeBaseId)
  const workflowsQuery = useWorkflows(
    { knowledgeBaseId: activeKnowledgeBaseId ?? undefined },
    { enabled: Boolean(activeKnowledgeBaseId) },
  )
  const knowledgeBaseDetailQuery = useKnowledgeBase(activeKnowledgeBaseId)
  const documentsQuery = useKnowledgeBaseDocuments(activeKnowledgeBaseId, {
    ...(documentStatusFilter === 'all' ? {} : { status: documentStatusFilter }),
  })
  const scoreRunsQuery = useScoreRuns(activeKnowledgeBaseId, { limit: 1 })
  const scoreRuns = scoreRunsQuery.data?.items ?? []
  const activeScoreRunId = selectedScoreRunId ?? scoreRuns[0]?.id ?? null
  const scoreRunQuery = useScoreRun(activeKnowledgeBaseId, activeScoreRunId)
  const documents = documentsQuery.data?.items ?? []
  const workflows = workflowsQuery.data?.items ?? []
  const activeDocumentId = documents.some((document) => document.id === selectedDocumentId)
    ? selectedDocumentId
    : documents[0]?.id ?? null
  const documentPreviewQuery = useKnowledgeBaseDocumentPreview(
    activeKnowledgeBaseId,
    activeDocumentId,
  )
  const knowledgeBase = knowledgeBaseDetailQuery.data ?? null
  // A brand-new knowledge base has no runs *because* it has nothing in it, and
  // the document inventory already says so; the timeline only earns its card
  // once there is something to time (UXA-305).
  const runTimelineVisible = documents.length > 0 || workflows.length > 0

  const createKnowledgeBaseMutation = useCreateKnowledgeBase()
  const deleteKnowledgeBaseMutation = useDeleteKnowledgeBase()
  const uploadMutation = useUploadKnowledgeBaseDocuments(activeKnowledgeBaseId)
  const deleteDocumentMutation = useDeleteKnowledgeBaseDocument(activeKnowledgeBaseId)
  const pushRecordsMutation = usePushRecords(activeKnowledgeBaseId)
  const uploadRecordFileMutation = useUploadRecordFile(activeKnowledgeBaseId)
  const startScoreRunMutation = useStartScoreRun(activeKnowledgeBaseId)
  const cancelScoreRunMutation = useCancelScoreRun(activeKnowledgeBaseId, activeScoreRunId)
  const replayScoreRunMutation = useReplayScoreRun(activeKnowledgeBaseId, activeScoreRunId)

  const feeds = domainConfigQuery.data?.records?.feeds ?? []
  const selectedFeed = feeds.find((feed) => feed.name === draft.selectedFeedName) ?? null
  const documentIssues = useMemo(
    () => validateDocumentFiles(draft.pendingFiles, domainConfigQuery.data?.validation),
    [draft.pendingFiles, domainConfigQuery.data?.validation],
  )
  const recordIssues = useMemo(
    () =>
      selectedFeed
        ? validateRecordRows(selectedFeed, draft.parsedRows, {
            recordFile: draft.pendingRecordFile,
          })
        : [],
    [selectedFeed, draft.parsedRows, draft.pendingRecordFile],
  )
  const requiredIssues = validateIngestionPrerequisites({
    knowledgeBaseId: activeKnowledgeBaseId,
    sourceType: draft.sourceType,
    feedName: draft.selectedFeedName,
  })
  const submitError =
    uploadMutation.error ?? uploadRecordFileMutation.error ?? pushRecordsMutation.error ?? null
  // A backend rejection belongs to the mutation that produced it: it clears
  // when that mutation is retried, without anyone remembering to clear it.
  const backendIssues: ValidationIssue[] = submitError
    ? [
        {
          id: 'ingestion-backend-error',
          source: 'backend',
          severity: 'error',
          message: apiErrorMessage(submitError, 'Submission failed.'),
        },
      ]
    : []
  const currentIssues = [
    ...requiredIssues,
    ...(draft.sourceType === 'documents' ? documentIssues : []),
    ...(draft.sourceType === 'records' ? recordIssues : []),
    ...draft.parseIssues,
    ...backendIssues,
  ]

  /** Write to the active knowledge base's draft; a no-op when none is selected. */
  function patchDraft(patch: Partial<IngestionDraft>) {
    if (activeKnowledgeBaseId) {
      updateDraft(activeKnowledgeBaseId, patch)
    }
  }

  function beginUpload(retry: () => void) {
    setUploadStatus('uploading')
    setUploadPercent(0)
    setUploadError(null)
    setRetryUpload(() => retry)
  }

  function reportUploadProgress(percent: number) {
    setUploadPercent(percent)
  }

  function runDocumentUpload(files: File[]) {
    beginUpload(() => runDocumentUpload(files))
    uploadMutation.mutate(
      { files, onUploadProgress: reportUploadProgress },
      {
        onSuccess: (response) => {
          const documentsLabel = countLabel(response.documents.length, 'document')

          setUploadStatus('done')
          setUploadPercent(100)
          setRetryUpload(null)
          // The submission is the server's business from here: the run and its
          // receipt arrive through GET /workflows. Nothing about it stays in
          // this tab's draft.
          if (activeKnowledgeBaseId) {
            clearDraft(activeKnowledgeBaseId)
          }
          showToast('success', `${documentsLabel} uploaded.`)
        },
        onError: (error) => {
          const message = apiErrorMessage(error, 'Document submission failed.')
          setUploadStatus('error')
          setUploadError(message)
          showToast('error', message)
        },
      },
    )
  }

  function runRecordFileUpload(feedName: string, file: File) {
    beginUpload(() => runRecordFileUpload(feedName, file))
    uploadRecordFileMutation.mutate(
      { feedName, file, onUploadProgress: reportUploadProgress },
      {
        onSuccess: (receipt) => {
          setUploadStatus('done')
          setUploadPercent(100)
          setRetryUpload(null)
          if (activeKnowledgeBaseId) {
            clearDraft(activeKnowledgeBaseId)
          }
          showToast('success', receiptToastMessage(receipt))
        },
        onError: (error) => {
          const message = apiErrorMessage(error, 'Records submission failed.')
          setUploadStatus('error')
          setUploadError(message)
          showToast('error', message)
        },
      },
    )
  }

  function submitDocuments() {
    const issues = [
      ...validateIngestionPrerequisites({
        knowledgeBaseId: activeKnowledgeBaseId,
        sourceType: 'documents',
        feedName: draft.selectedFeedName,
      }),
      ...validateDocumentFiles(draft.pendingFiles, domainConfigQuery.data?.validation),
    ]

    if (issues.some((issue) => issue.severity === 'error')) {
      patchDraft({ parseIssues: issues })
      return
    }

    runDocumentUpload(draft.pendingFiles)
  }

  function submitRecords() {
    const recordFileIssues = selectedFeed?.source === 'file_upload'
      ? validateRecordFile(draft.pendingRecordFile)
      : []
    const issues = [
      ...validateIngestionPrerequisites({
        knowledgeBaseId: activeKnowledgeBaseId,
        sourceType: 'records',
        feedName: draft.selectedFeedName,
      }),
      ...recordFileIssues,
      ...(selectedFeed
        ? validateRecordRows(selectedFeed, draft.parsedRows, {
            recordFile: draft.pendingRecordFile,
          })
        : []),
    ]

    if (issues.some((issue) => issue.severity === 'error') || !selectedFeed) {
      patchDraft({ parseIssues: issues })
      return
    }

    if (selectedFeed.source === 'file_upload') {
      const recordFile = draft.pendingRecordFile
      if (!recordFile) {
        patchDraft({ parseIssues: recordFileIssues })
        return
      }
      runRecordFileUpload(selectedFeed.name, recordFile)
      return
    }

    pushRecordsMutation.mutate(
      {
        feed_name: selectedFeed.name,
        rows: draft.parsedRows,
      },
      {
        onSuccess: (receipt) => {
          if (activeKnowledgeBaseId) {
            clearDraft(activeKnowledgeBaseId)
          }
          showToast('success', receiptToastMessage(receipt))
        },
        onError: (error) => {
          const message = apiErrorMessage(error, 'Records submission failed.')
          showToast('error', message)
        },
      },
    )
  }

  function runIngestion() {
    if (draft.sourceType === 'documents') {
      submitDocuments()
      return
    }

    if (draft.sourceType === 'records') {
      submitRecords()
      return
    }

    patchDraft({
      parseIssues: validateIngestionPrerequisites({
        knowledgeBaseId: activeKnowledgeBaseId,
        sourceType: draft.sourceType,
        feedName: draft.selectedFeedName,
      }),
    })
  }

  if (knowledgeBasesQuery.isLoading || domainConfigQuery.isLoading) {
    return <LoadingState label="Loading knowledge bases" />
  }

  if (knowledgeBasesQuery.isError || domainConfigQuery.isError) {
    return <ErrorState description="Your knowledge bases could not be loaded. Try again in a moment." />
  }

  if (!knowledgeBasesQuery.data || !domainConfigQuery.data) {
    return <LoadingState label="Waiting for knowledge base configuration" />
  }

  if (activeKnowledgeBaseId && (knowledgeBaseDetailQuery.isLoading || documentsQuery.isLoading)) {
    return <LoadingState label="Loading selected knowledge base" />
  }

  if (knowledgeBaseDetailQuery.isError || documentsQuery.isError) {
    return <ErrorState description="This knowledge base could not be opened. Try again, or pick another one." />
  }

  const canRunIngestion =
    (draft.sourceType === 'documents' &&
      draft.pendingFiles.length > 0 &&
      documentIssues.every((issue) => issue.severity !== 'error')) ||
    (draft.sourceType === 'records' &&
      selectedFeed !== null &&
      (selectedFeed.source !== 'file_upload' || draft.pendingRecordFile !== null) &&
      draft.parsedRows.length > 0 &&
      recordIssues.every((issue) => issue.severity !== 'error'))
  const runPending = uploadMutation.isPending || pushRecordsMutation.isPending || uploadRecordFileMutation.isPending
  // This tab just handed a submission to the server. It says nothing about
  // history — the run timeline is the record of what happened — only that the
  // handoff succeeded and the run has yet to surface in the poll.
  const submissionAccepted =
    uploadStatus === 'done' || uploadMutation.isSuccess || pushRecordsMutation.isSuccess

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
                      setSelectedDocumentId(null)
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
                setSelectedDocumentId(null)
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
                    setSelectedDocumentId(null)
                    setActiveScoreRunId(null)
                  },
                })
              }}
              open={confirmingKnowledgeBaseDelete}
              title="Delete knowledge base"
            />
          </Card>

          <Card>
            <section
              aria-labelledby="ingestion-step-stage"
              className="ingestion-step-section"
              ref={sourceStepRef}
            >
              <div className="ingestion-step-section__header">
                <strong id="ingestion-step-stage">Step 1 — Stage ingestion source</strong>
                <p className="page-copy-block">
                  Choose a source and prepare documents or structured records for review.
                </p>
              </div>
              <SourceTypeStep
                selectedSourceType={draft.sourceType}
                onChange={(sourceType) => {
                  patchDraft({ sourceType: sourceType })
                }}
              />

              {draft.sourceType === 'documents' ? (
                <DocumentSourcePanel
                  acceptContentTypes={domainConfigQuery.data?.validation.allowed_content_types}
                  files={draft.pendingFiles}
                  onFilesChange={(files) => {
                    patchDraft({ pendingFiles: files })
                    patchDraft({ parseIssues: [] })
                  }}
                />
              ) : null}

              {draft.sourceType === 'records' ? (
                <RecordsSourcePanel
                  feeds={feeds}
                  issues={recordIssues}
                  showPreviewTable={false}
                  onDraftChange={() => {
                    patchDraft({ parsedRows: [] })
                    patchDraft({ parseIssues: [] })
                  }}
                  onFileChange={(file) => {
                    patchDraft({ pendingRecordFile: file })
                  }}
                  rows={draft.parsedRows}
                  recordFile={draft.pendingRecordFile}
                  selectedFeedName={draft.selectedFeedName}
                  onFeedChange={(feedName) => {
                    patchDraft({ selectedFeedName: feedName })
                    patchDraft({ pendingRecordFile: null })
                  }}
                  onRowsParsed={(rows, parseIssues) => {
                    patchDraft({ parsedRows: rows })
                    patchDraft({ parseIssues })
                  }}
                />
              ) : null}
            </section>
          </Card>

          <Card>
            <section className="ingestion-step-section" aria-labelledby="ingestion-step-review">
              <div className="ingestion-step-section__header">
                <strong id="ingestion-step-review">Step 2 — Review and run ingestion</strong>
                <p className="page-copy-block">
                  Validate staged content, review previews, then run ingestion.
                </p>
              </div>

              {draft.sourceType === 'records' ? (
                <RecordsPreviewTable
                  rows={draft.parsedRows}
                  issues={recordIssues}
                  emptyDescription="Parse records to review staged rows before running ingestion."
                />
              ) : null}

              <ValidationPanel issues={currentIssues} />
              <SubmitPanel
                sourceType={draft.sourceType}
                canRunIngestion={canRunIngestion}
                runPending={runPending}
                onRunIngestion={runIngestion}
              />
              <UploadProgress
                label={
                  draft.sourceType === 'documents'
                    ? 'Document upload progress'
                    : 'Records upload progress'
                }
                status={uploadStatus}
                percent={uploadPercent}
                error={uploadError ?? undefined}
                onRetry={() => retryUpload?.()}
              />
            </section>
          </Card>
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

          <Card>
            <DocumentInventory
              activeDocumentId={activeDocumentId}
              deleteDisabled={deleteDocumentMutation.isPending}
              documents={documents}
              statusFilter={documentStatusFilter}
              onStatusFilterChange={setDocumentStatusFilter}
              preview={documentPreviewQuery.data ?? null}
              previewError={documentPreviewQuery.isError}
              previewLoading={documentPreviewQuery.isLoading}
              onDeleteDocument={(documentId) => setConfirmingDocumentDeleteId(documentId)}
              onSelectDocument={setSelectedDocumentId}
              onStageSource={() => {
                const section = sourceStepRef.current
                if (section && typeof section.scrollIntoView === 'function') {
                  section.scrollIntoView({ behavior: 'smooth', block: 'start' })
                }
              }}
            />
            <ConfirmDialog
              body={`Removes ${
                documents.find((document) => document.id === confirmingDocumentDeleteId)
                  ?.filename ?? 'this document'
              } and the graph and vector artifacts built from it.`}
              confirmLabel="Remove document"
              destructive
              onCancel={() => setConfirmingDocumentDeleteId(null)}
              onConfirm={() => {
                const documentId = confirmingDocumentDeleteId
                setConfirmingDocumentDeleteId(null)
                if (!documentId) {
                  return
                }
                deleteDocumentMutation.mutate(documentId, {
                  onSuccess: () => setSelectedDocumentId(null),
                })
              }}
              open={confirmingDocumentDeleteId !== null}
              title="Remove document"
            />
          </Card>
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

/** Lifecycle states worth filtering by; the in-progress states churn too fast. */
const DOCUMENT_STATUS_FILTERS = ['all', 'validated', 'extracted_empty', 'failed'] as const

type DocumentInventoryProps = {
  activeDocumentId: string | null
  deleteDisabled: boolean
  documents: KnowledgeBaseDocumentListResponse['items']
  preview: KnowledgeBaseDocumentPreviewResponse | null
  previewLoading: boolean
  previewError: boolean
  statusFilter: string
  onStatusFilterChange: (status: string) => void
  onStageSource: () => void
  onDeleteDocument: (documentId: string) => void
  onSelectDocument: (documentId: string) => void
}

function DocumentInventory({
  activeDocumentId,
  deleteDisabled,
  documents,
  preview,
  previewLoading,
  previewError,
  statusFilter,
  onStatusFilterChange,
  onDeleteDocument,
  onSelectDocument,
  onStageSource,
}: DocumentInventoryProps) {
  // Which row has its warning reasons open. Reasons used to be reachable only
  // by hovering a `title` or by selecting the row — undiscoverable, and dead on
  // touch.
  const [expandedWarningsId, setExpandedWarningsId] = useState<string | null>(null)

  return (
    <section className="ingestion-studio-documents" aria-labelledby="document-inventory-title">
      <div className="metric-row">
        <strong id="document-inventory-title">Document inventory</strong>
        <Chip label={`${documents.length} tracked`} tone="network" />
      </div>

      {/* Its own row: sharing the heading's flex line squeezed the select below
          its widest option in the 320px context rail. */}
      <label className="ingestion-document-filter">
        <span className="metric-row__label">Filter documents by status</span>
        <select
          aria-label="Filter documents by status"
          className="page-input ingestion-document-filter__select"
          onChange={(event) => onStatusFilterChange(event.target.value)}
          value={statusFilter}
        >
          {DOCUMENT_STATUS_FILTERS.map((value) => (
            <option key={value} value={value}>
              {value === 'all' ? 'All statuses' : statusToken('document', value).label}
            </option>
          ))}
        </select>
      </label>

      {documents.length > 0 ? (
        <div className="knowledge-base-documents">
          {documents.map((document) => {
            const warningReasons = document.warning_reasons ?? []
            const droppedEntities = document.dropped_entity_count ?? 0
            const droppedRelationships = document.dropped_relationship_count ?? 0

            return (
              <div className="knowledge-base-document-row" key={document.id}>
                <button
                  className={
                    activeDocumentId === document.id
                      ? 'page-list-item page-list-item--active'
                      : 'page-list-item'
                  }
                  onClick={() => onSelectDocument(document.id)}
                  type="button"
                >
                  <strong>{document.filename}</strong>
                  <span className="metric-row__label">
                    {formatFileSize(document.size_bytes)} | {formatTimestamp(document.created_at)}
                  </span>
                  <span className="alert-row-card__meta">
                    {/* The durable lifecycle, not the registration status: the
                        latter says "ready" for a document that produced nothing. */}
                    <StatusChip
                      kind="document"
                      status={document.current_status ?? document.status}
                    />
                    {warningReasons.length > 0 || (document.warning_count ?? 0) > 0 ? (
                      <Chip label={countLabel(document.warning_count ?? 0, 'warning')} tone="warning" />
                    ) : null}
                  </span>
                  {document.last_error ? (
                    <span className="ingestion-document-row__error" role="alert">
                      {document.last_error}
                    </span>
                  ) : null}
                  {droppedEntities > 0 || droppedRelationships > 0 ? (
                    // Exact counts only: how many of each were kept is not
                    // knowable from this payload, so it is not claimed.
                    <span className="metric-row__label">
                      {[
                        droppedEntities > 0
                          ? `${countLabel(droppedEntities, 'entity', 'entities')} dropped`
                          : null,
                        droppedRelationships > 0
                          ? `${countLabel(droppedRelationships, 'relationship')} dropped`
                          : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  ) : null}
                </button>
                {warningReasons.length > 0 ? (
                  <button
                    aria-expanded={expandedWarningsId === document.id}
                    className="page-button page-button--sm page-button--secondary"
                    onClick={() =>
                      setExpandedWarningsId((current) =>
                        current === document.id ? null : document.id,
                      )
                    }
                    type="button"
                  >
                    {expandedWarningsId === document.id ? 'Hide' : 'Show'}{' '}
                    {countLabel(warningReasons.length, 'warning')}
                  </button>
                ) : null}
                {expandedWarningsId === document.id ? (
                  <ul className="metric-row__label" data-testid="document-warning-reasons">
                    {warningReasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                    {(document.drop_sample_reasons ?? []).map((reason) => (
                      <li key={`drop-${reason}`}>{reason}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            )
          })}
        </div>
      ) : (
        <EmptyState
          action={
            <button
              className="page-button page-button--sm page-button--primary"
              onClick={onStageSource}
              type="button"
            >
              Stage a source
            </button>
          }
          description="Register policy, claims, or reference documents to start ingestion."
          title="No documents yet"
        />
      )}

      {activeDocumentId ? (
        <button
          className="page-button page-button--secondary"
          disabled={deleteDisabled}
          onClick={() => onDeleteDocument(activeDocumentId)}
          type="button"
        >
          Remove document
        </button>
      ) : null}

      {/* With no documents at all, the inventory's empty state has already said
          so; a second "no document selected" and a third "no runs yet" made one
          screen state the same fact three times (UXA-305). There is nothing to
          preview until something has been ingested. */}
      {documents.length === 0 ? null : (
        <section className="ingestion-document-preview" aria-labelledby="document-preview-title">
          <div className="metric-row">
            <strong id="document-preview-title">Document preview</strong>
            {preview?.truncated ? <Chip label="Truncated" tone="warning" /> : null}
          </div>

          {!activeDocumentId ? (
            <EmptyState
              title="No document selected"
              description="Select a document in inventory to review its preview."
            />
          ) : previewLoading ? (
            <LoadingState label="Loading document preview" />
          ) : previewError ? (
            <ErrorState description="Document preview could not be loaded from the API." />
          ) : preview ? (
            preview.preview_text.trim().length > 0 ? (
              <article className="ingestion-document-preview__content">
                <p className="metric-row__label">
                  {countLabel(preview.line_count, 'line')} from {preview.filename}
                </p>
                <pre>{preview.preview_text}</pre>
              </article>
            ) : (
              <EmptyState
                title="No preview text returned"
                description="This document has no text preview content yet."
              />
            )
          ) : null}
        </section>
      )}
    </section>
  )
}

function receiptToastMessage(receipt: RecordIngestReceipt): string {
  if (receipt.duplicate) {
    return `Duplicate submission for ${receipt.feed_name} (no-op).`
  }

  const parts = [`${receipt.accepted_count} accepted`]
  if (receipt.duplicate_count > 0) {
    parts.push(`${receipt.duplicate_count} duplicate`)
  }
  if (receipt.rejected_count > 0) {
    parts.push(`${receipt.rejected_count} rejected`)
  }
  return `${parts.join(', ')} for ${receipt.feed_name}.`
}
