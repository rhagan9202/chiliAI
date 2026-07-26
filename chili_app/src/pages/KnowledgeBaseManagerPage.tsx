import { useState } from 'react'
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
import type {
  KnowledgeBaseDocumentPreviewResponse,
  RecordIngestReceipt,
} from '../api/contracts'
import { useWorkflows } from '../api/workflows'
import { DocumentSourcePanel } from '../components/ingestion/DocumentSourcePanel'
import { IngestionStepper } from '../components/ingestion/IngestionStepper'
import { KnowledgeBaseSelector } from '../components/ingestion/KnowledgeBaseSelector'
import { isDomainMismatch } from '../components/knowledgebase/domainMismatch'
import { KbDomainBadge } from '../components/knowledgebase/KbDomainBadge'
import { RecordsSourcePanel } from '../components/ingestion/RecordsSourcePanel'
import { RecordsPreviewTable } from '../components/ingestion/RecordsPreviewTable'
import { RunTimeline } from '../components/ingestion/RunTimeline'
import { SourceTypeStep } from '../components/ingestion/SourceTypeStep'
import { SubmitPanel } from '../components/ingestion/SubmitPanel'
import { UploadProgress } from '../components/ingestion/UploadProgress'
import type { UploadStatus } from '../components/ingestion/UploadProgress'
import { ValidationPanel } from '../components/ingestion/ValidationPanel'
import { showToast } from '../components/common/toastStore'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import {
  validateDocumentFiles,
  validateRecordFile,
  validateRecordRows,
  validateRequiredWizardState,
} from '../lib/ingestion/validateIngestion'
import { apiErrorMessage } from '../lib/apiClient'
import { useIngestionStudioStore } from '../stores/ingestionStudioStore'
import './pages.css'

export function KnowledgeBaseManagerPage() {
  const navigate = useNavigate()
  const studio = useIngestionStudioStore()
  const knowledgeBasesQuery = useKnowledgeBases()
  const domainConfigQuery = useDomainConfig()
  // Honor a ?kb= deep-link as the initial selection, matching the convention on
  // AlertFeedPage / PolicyIntelligencePage / InvestigationWorkbenchPage. If the
  // requested KB isn't in the visible list, the auto-select fallback below wins.
  // Initializer-only: a client-side navigation that changes ?kb= without
  // remounting this page will not rebind selection — no in-app link carries
  // ?kb= here today; revisit if one is added.
  const [searchParams] = useSearchParams()
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<string | null>(
    () => searchParams.get('kb'),
  )
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null)
  const [knowledgeBaseName, setKnowledgeBaseName] = useState('')
  const [knowledgeBaseDescription, setKnowledgeBaseDescription] = useState('')
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle')
  const [uploadPercent, setUploadPercent] = useState(0)
  const [uploadError, setUploadError] = useState<string | null>(null)
  // Holds the last upload invocation so the Retry button can re-run it verbatim.
  const [retryUpload, setRetryUpload] = useState<(() => void) | null>(null)
  const [showAllDomains, setShowAllDomains] = useState(false)

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
  const documentsQuery = useKnowledgeBaseDocuments(activeKnowledgeBaseId)
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

  const createKnowledgeBaseMutation = useCreateKnowledgeBase()
  const deleteKnowledgeBaseMutation = useDeleteKnowledgeBase()
  const uploadMutation = useUploadKnowledgeBaseDocuments(activeKnowledgeBaseId)
  const deleteDocumentMutation = useDeleteKnowledgeBaseDocument(activeKnowledgeBaseId)
  const pushRecordsMutation = usePushRecords(activeKnowledgeBaseId)
  const uploadRecordFileMutation = useUploadRecordFile(activeKnowledgeBaseId)

  const feeds = domainConfigQuery.data?.records?.feeds ?? []
  const selectedFeed = feeds.find((feed) => feed.name === studio.selectedFeedName) ?? null
  const documentIssues = validateDocumentFiles(
    studio.pendingFiles,
    domainConfigQuery.data?.validation,
  )
  const recordIssues = selectedFeed
    ? validateRecordRows(selectedFeed, studio.parsedRows, {
        recordFile: studio.pendingRecordFile,
      })
    : []
  const requiredIssues = validateRequiredWizardState({
    knowledgeBaseId: activeKnowledgeBaseId,
    sourceType: studio.sourceType,
    feedName: studio.selectedFeedName,
  })
  const currentIssues = [
    ...requiredIssues,
    ...(studio.sourceType === 'documents' ? documentIssues : []),
    ...(studio.sourceType === 'records' ? recordIssues : []),
    ...studio.validationIssues,
  ]

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
          const count = response.documents.length
          const suffix = count === 1 ? 'document' : 'documents'

          setUploadStatus('done')
          setUploadPercent(100)
          setRetryUpload(null)
          studio.setValidationIssues([])
          studio.addReceipt({
            id: `documents-${response.documents.map((document) => document.source_document_id).join('-')}`,
            sourceType: 'documents',
            status: 'accepted',
            message: `${count} ${suffix} accepted.`,
            createdAt: response.documents[0]?.created_at ?? new Date().toISOString(),
          })
          studio.setPendingFiles([])
          studio.setCurrentStep('runs')
          showToast('success', `${count} ${suffix} uploaded.`)
        },
        onError: (error) => {
          const message = apiErrorMessage(error, 'Document submission failed.')
          setUploadStatus('error')
          setUploadError(message)
          studio.addValidationIssues([
            {
              id: `documents-backend-error-${Date.now()}`,
              source: 'backend',
              severity: 'error',
              message,
            },
          ])
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
          studio.setValidationIssues([])
          studio.addReceipt({
            id: `records-${receipt.correlation_id}`,
            sourceType: 'records',
            status: 'accepted',
            message: `${receipt.accepted_count} records accepted for ${receipt.feed_name}.`,
            createdAt: receipt.created_at,
            receipt,
          })
          studio.setCurrentStep('runs')
          showToast('success', receiptToastMessage(receipt))
        },
        onError: (error) => {
          const message = apiErrorMessage(error, 'Records submission failed.')
          setUploadStatus('error')
          setUploadError(message)
          studio.addValidationIssues([
            {
              id: `records-backend-error-${Date.now()}`,
              source: 'backend',
              severity: 'error',
              message,
            },
          ])
          showToast('error', message)
        },
      },
    )
  }

  function submitDocuments() {
    const issues = [
      ...validateRequiredWizardState({
        knowledgeBaseId: activeKnowledgeBaseId,
        sourceType: 'documents',
        feedName: studio.selectedFeedName,
      }),
      ...validateDocumentFiles(studio.pendingFiles, domainConfigQuery.data?.validation),
    ]

    if (issues.some((issue) => issue.severity === 'error')) {
      studio.setValidationIssues(issues)
      return
    }

    runDocumentUpload(studio.pendingFiles)
  }

  function submitRecords() {
    const recordFileIssues = selectedFeed?.source === 'file_upload'
      ? validateRecordFile(studio.pendingRecordFile)
      : []
    const issues = [
      ...validateRequiredWizardState({
        knowledgeBaseId: activeKnowledgeBaseId,
        sourceType: 'records',
        feedName: studio.selectedFeedName,
      }),
      ...recordFileIssues,
      ...(selectedFeed
        ? validateRecordRows(selectedFeed, studio.parsedRows, {
            recordFile: studio.pendingRecordFile,
          })
        : []),
    ]

    if (issues.some((issue) => issue.severity === 'error') || !selectedFeed) {
      studio.setValidationIssues(issues)
      return
    }

    if (selectedFeed.source === 'file_upload') {
      const recordFile = studio.pendingRecordFile
      if (!recordFile) {
        studio.setValidationIssues(recordFileIssues)
        return
      }
      runRecordFileUpload(selectedFeed.name, recordFile)
      return
    }

    pushRecordsMutation.mutate(
      {
        feed_name: selectedFeed.name,
        rows: studio.parsedRows,
      },
      {
        onSuccess: (receipt) => {
          studio.setValidationIssues([])
          studio.addReceipt({
            id: `records-${receipt.correlation_id}`,
            sourceType: 'records',
            status: 'accepted',
            message: `${receipt.accepted_count} records accepted for ${receipt.feed_name}.`,
            createdAt: receipt.created_at,
            receipt,
          })
          studio.setCurrentStep('runs')
          showToast('success', receiptToastMessage(receipt))
        },
        onError: (error) => {
          const message = apiErrorMessage(error, 'Records submission failed.')
          studio.addValidationIssues([
            {
              id: `records-backend-error-${Date.now()}`,
              source: 'backend',
              severity: 'error',
              message,
            },
          ])
          showToast('error', message)
        },
      },
    )
  }

  function runIngestion() {
    if (studio.sourceType === 'documents') {
      submitDocuments()
      return
    }

    if (studio.sourceType === 'records') {
      submitRecords()
      return
    }

    studio.setValidationIssues(
      validateRequiredWizardState({
        knowledgeBaseId: activeKnowledgeBaseId,
        sourceType: studio.sourceType,
        feedName: studio.selectedFeedName,
      }),
    )
  }

  if (knowledgeBasesQuery.isLoading || domainConfigQuery.isLoading) {
    return <LoadingState label="Loading ingestion studio" />
  }

  if (knowledgeBasesQuery.isError || domainConfigQuery.isError) {
    return <ErrorState description="Ingestion Studio configuration could not be loaded from the API." />
  }

  if (!knowledgeBasesQuery.data || !domainConfigQuery.data) {
    return <LoadingState label="Waiting for ingestion studio configuration" />
  }

  if (activeKnowledgeBaseId && (knowledgeBaseDetailQuery.isLoading || documentsQuery.isLoading)) {
    return <LoadingState label="Loading selected knowledge base" />
  }

  if (knowledgeBaseDetailQuery.isError || documentsQuery.isError) {
    return <ErrorState description="Selected knowledge base detail could not be loaded from the API." />
  }

  const contentErrors = currentIssues.filter(
    (item) => (item.kind ?? 'content') === 'content' && item.severity === 'error',
  )
  const userHasSubmittableState =
    Boolean(activeKnowledgeBaseId) &&
    Boolean(studio.sourceType) &&
    (studio.pendingFiles.length > 0 || studio.parsedRows.length > 0)
  const canRunIngestion =
    (studio.sourceType === 'documents' &&
      studio.pendingFiles.length > 0 &&
      documentIssues.every((issue) => issue.severity !== 'error')) ||
    (studio.sourceType === 'records' &&
      selectedFeed !== null &&
      (selectedFeed.source !== 'file_upload' || studio.pendingRecordFile !== null) &&
      studio.parsedRows.length > 0 &&
      recordIssues.every((issue) => issue.severity !== 'error'))
  const runPending = uploadMutation.isPending || pushRecordsMutation.isPending || uploadRecordFileMutation.isPending

  const completedStepIds = new Set([
    ...(activeKnowledgeBaseId ? (['knowledge-base'] as const) : []),
    ...(studio.sourceType ? (['source'] as const) : []),
    ...(studio.pendingFiles.length > 0 || studio.parsedRows.length > 0 ? (['preview'] as const) : []),
    ...(userHasSubmittableState && contentErrors.length === 0 ? (['validate'] as const) : []),
    ...(studio.receipts.length > 0 ? (['submit'] as const) : []),
  ])
  const errorStepIds = new Set(contentErrors.length > 0 ? (['validate'] as const) : [])

  const activeKnowledgeBaseSearch = knowledgeBaseSearch(activeKnowledgeBaseId)

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label="Documents + records" tone="info" />}
        eyebrow="Ingestion control"
        subtitle="Guide documents and config-defined structured records into the selected knowledge base."
        title="Ingestion Studio"
      />

      <div className="ingestion-studio-layout">
        <Card>
          <IngestionStepper
            currentStep={studio.currentStep}
            completedStepIds={completedStepIds}
            errorStepIds={errorStepIds}
          />
        </Card>

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
                      setKnowledgeBaseName('')
                      setKnowledgeBaseDescription('')
                      studio.setCurrentStep('source')
                    },
                  },
                )
              }}
              onDelete={(knowledgeBaseId) => {
                deleteKnowledgeBaseMutation.mutate(knowledgeBaseId, {
                  onSuccess: () => {
                    setSelectedKnowledgeBaseId(null)
                    setSelectedDocumentId(null)
                    studio.setCurrentStep('knowledge-base')
                  },
                })
              }}
              onSelect={(knowledgeBaseId) => {
                setSelectedKnowledgeBaseId(knowledgeBaseId)
                setSelectedDocumentId(null)
                studio.setCurrentStep('source')
              }}
              onToggleShowAllDomains={() => setShowAllDomains((value) => !value)}
              showAllDomains={showAllDomains}
            />
          </Card>

          <Card>
            <section className="ingestion-step-section" aria-labelledby="ingestion-step-stage">
              <div className="ingestion-step-section__header">
                <strong id="ingestion-step-stage">Step 1 — Stage ingestion source</strong>
                <p className="page-copy-block">
                  Choose a source and prepare documents or structured records for review.
                </p>
              </div>
              <SourceTypeStep
                selectedSourceType={studio.sourceType}
                onChange={(sourceType) => {
                  studio.setSourceType(sourceType)
                  studio.setCurrentStep('preview')
                }}
              />

              {studio.sourceType === 'documents' ? (
                <DocumentSourcePanel
                  files={studio.pendingFiles}
                  onFilesChange={(files) => {
                    studio.setPendingFiles(files)
                    studio.setValidationIssues([])
                    studio.setCurrentStep('validate')
                  }}
                />
              ) : null}

              {studio.sourceType === 'records' ? (
                <RecordsSourcePanel
                  feeds={feeds}
                  issues={recordIssues}
                  showPreviewTable={false}
                  onDraftChange={() => {
                    studio.setParsedRows([])
                    studio.setValidationIssues([])
                    studio.setCurrentStep('preview')
                  }}
                  onFileChange={(file) => {
                    studio.setPendingRecordFile(file)
                  }}
                  rows={studio.parsedRows}
                  recordFile={studio.pendingRecordFile}
                  selectedFeedName={studio.selectedFeedName}
                  onFeedChange={(feedName) => {
                    studio.setSelectedFeedName(feedName)
                    studio.setPendingRecordFile(null)
                  }}
                  onRowsParsed={(rows, parseIssues) => {
                    studio.setParsedRows(rows)
                    studio.setValidationIssues(parseIssues)
                    studio.setCurrentStep('validate')
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

              {studio.sourceType === 'records' ? (
                <RecordsPreviewTable
                  rows={studio.parsedRows}
                  issues={recordIssues}
                  emptyDescription="Parse records to review staged rows before running ingestion."
                />
              ) : null}

              <ValidationPanel issues={currentIssues} />
              <SubmitPanel
                sourceType={studio.sourceType}
                canRunIngestion={canRunIngestion}
                runPending={runPending}
                onRunIngestion={runIngestion}
              />
              <UploadProgress
                label={
                  studio.sourceType === 'documents'
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
              hasReceipts={studio.receipts.length > 0}
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
              onWatchRuns={() => studio.setCurrentStep('runs')}
            />
          </Card>

          <Card>
            <RunTimeline
              receipts={studio.receipts}
              workflows={workflows}
            />
          </Card>

          <Card>
            <DocumentInventory
              activeDocumentId={activeDocumentId}
              deleteDisabled={deleteDocumentMutation.isPending}
              documents={documents}
              preview={documentPreviewQuery.data ?? null}
              previewError={documentPreviewQuery.isError}
              previewLoading={documentPreviewQuery.isLoading}
              onDeleteDocument={(documentId) => {
                deleteDocumentMutation.mutate(documentId, {
                  onSuccess: () => setSelectedDocumentId(null),
                })
              }}
              onSelectDocument={setSelectedDocumentId}
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
  hasReceipts,
  hasWorkflows,
  onInvestigateEntities,
  onReviewAlerts,
  onWatchRuns,
}: {
  activeKnowledgeBaseId: string | null
  hasReceipts: boolean
  hasWorkflows: boolean
  onInvestigateEntities: () => void
  onReviewAlerts: () => void
  onWatchRuns: () => void
}) {
  const disabled = !activeKnowledgeBaseId
  const message = hasWorkflows
    ? 'Runs are updating for this knowledge base.'
    : hasReceipts
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
          onClick={onWatchRuns}
          type="button"
        >
          Watch runs
        </button>
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
        <Chip label={knowledgeBase.status} tone={toneForKnowledgeBaseStatus(knowledgeBase.status)} />
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

type DocumentInventoryProps = {
  activeDocumentId: string | null
  deleteDisabled: boolean
  documents: Array<{
    id: string
    filename: string
    size_bytes?: number | null
    status: string
    created_at: string
    warning_count?: number
    warning_reasons?: string[]
  }>
  preview: KnowledgeBaseDocumentPreviewResponse | null
  previewLoading: boolean
  previewError: boolean
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
  onDeleteDocument,
  onSelectDocument,
}: DocumentInventoryProps) {
  return (
    <section className="ingestion-studio-documents" aria-labelledby="document-inventory-title">
      <div className="metric-row">
        <strong id="document-inventory-title">Document inventory</strong>
        <Chip label={`${documents.length} tracked`} tone="network" />
      </div>

      {documents.length > 0 ? (
        <div className="knowledge-base-documents">
          {documents.map((document) => (
            <button
              className={
                activeDocumentId === document.id
                  ? 'page-list-item page-list-item--active'
                  : 'page-list-item'
              }
              key={document.id}
              onClick={() => onSelectDocument(document.id)}
              type="button"
            >
              <strong>{document.filename}</strong>
              <span className="metric-row__label">
                {formatFileSize(document.size_bytes)} | {formatTimestamp(document.created_at)}
              </span>
              <span className="alert-row-card__meta">
                <Chip label={document.status} tone={toneForDocumentStatus(document.status)} />
                {(document.warning_count ?? 0) > 0 ? (
                  <span title={(document.warning_reasons ?? []).join('\n')}>
                    <Chip
                      label={`${document.warning_count} warning${document.warning_count === 1 ? '' : 's'}`}
                      tone="warning"
                    />
                  </span>
                ) : null}
              </span>
              {activeDocumentId === document.id &&
              (document.warning_reasons ?? []).length > 0 ? (
                <ul className="metric-row__label" data-testid="document-warning-reasons">
                  {(document.warning_reasons ?? []).map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              ) : null}
            </button>
          ))}
        </div>
      ) : (
        <EmptyState
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
                {preview.line_count} line{preview.line_count === 1 ? '' : 's'} from {preview.filename}
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

function formatTimestamp(value: string | null) {
  if (!value) {
    return 'Not yet recorded'
  }

  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function formatFileSize(sizeBytes: number | null) {
  if (!sizeBytes) {
    return 'Unknown size'
  }

  if (sizeBytes < 1024) {
    return `${sizeBytes} B`
  }

  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`
  }

  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`
}

function toneForKnowledgeBaseStatus(status: 'active' | 'building' | 'ready' | 'error' | 'archived') {
  switch (status) {
    case 'ready':
      return 'success' as const
    case 'active':
    case 'building':
      return 'warning' as const
    case 'error':
      return 'danger' as const
    case 'archived':
      return 'default' as const
  }
}

function toneForDocumentStatus(status: string) {
  if (status === 'ready' || status === 'validated') {
    return 'success' as const
  }
  if (status === 'failed' || status === 'error') {
    return 'danger' as const
  }
  return 'warning' as const
}
