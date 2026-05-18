import { useState } from 'react'

import { useDomainConfig } from '../api/config'
import {
  useCreateKnowledgeBase,
  useDeleteKnowledgeBase,
  useDeleteKnowledgeBaseDocument,
  useKnowledgeBase,
  useKnowledgeBaseDocuments,
  useKnowledgeBases,
  useUploadKnowledgeBaseDocuments,
} from '../api/knowledgebases'
import { usePushRecords, useUploadRecordFile } from '../api/records'
import { useWorkflows } from '../api/workflows'
import { DocumentSourcePanel } from '../components/ingestion/DocumentSourcePanel'
import { IngestionStepper } from '../components/ingestion/IngestionStepper'
import { KnowledgeBaseSelector } from '../components/ingestion/KnowledgeBaseSelector'
import { RecordsSourcePanel } from '../components/ingestion/RecordsSourcePanel'
import { RunTimeline } from '../components/ingestion/RunTimeline'
import { SourceTypeStep } from '../components/ingestion/SourceTypeStep'
import { SubmitPanel } from '../components/ingestion/SubmitPanel'
import { ValidationPanel } from '../components/ingestion/ValidationPanel'
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
  const studio = useIngestionStudioStore()
  const knowledgeBasesQuery = useKnowledgeBases()
  const domainConfigQuery = useDomainConfig()
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<string | null>(null)
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null)
  const [knowledgeBaseName, setKnowledgeBaseName] = useState('')
  const [knowledgeBaseDescription, setKnowledgeBaseDescription] = useState('')

  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const activeKnowledgeBaseId = knowledgeBases.some((item) => item.id === selectedKnowledgeBaseId)
    ? selectedKnowledgeBaseId
    : knowledgeBases[0]?.id ?? null
  const workflowsQuery = useWorkflows(
    { knowledgeBaseId: activeKnowledgeBaseId ?? undefined },
    { enabled: Boolean(activeKnowledgeBaseId) },
  )
  const knowledgeBaseDetailQuery = useKnowledgeBase(activeKnowledgeBaseId)
  const documentsQuery = useKnowledgeBaseDocuments(activeKnowledgeBaseId)
  const documents = documentsQuery.data?.items ?? []
  const activeDocumentId = documents.some((document) => document.id === selectedDocumentId)
    ? selectedDocumentId
    : documents[0]?.id ?? null
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
    ? validateRecordRows(selectedFeed, studio.parsedRows)
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

    uploadMutation.mutate(studio.pendingFiles, {
      onSuccess: (response) => {
        const count = response.documents.length
        const suffix = count === 1 ? 'document' : 'documents'

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
      },
      onError: (error) => {
        studio.addValidationIssues([
          {
            id: `documents-backend-error-${Date.now()}`,
            source: 'backend',
            severity: 'error',
            message: apiErrorMessage(error, 'Document submission failed.'),
          },
        ])
      },
    })
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
      ...(selectedFeed ? validateRecordRows(selectedFeed, studio.parsedRows) : []),
    ]

    if (issues.some((issue) => issue.severity === 'error') || !selectedFeed) {
      studio.setValidationIssues(issues)
      return
    }

    if (selectedFeed.source === 'file_upload') {
      if (!studio.pendingRecordFile) {
        studio.setValidationIssues(recordFileIssues)
        return
      }
      uploadRecordFileMutation.mutate(
        {
          feedName: selectedFeed.name,
          file: studio.pendingRecordFile,
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
          },
          onError: (error) => {
            studio.addValidationIssues([
              {
                id: `records-backend-error-${Date.now()}`,
                source: 'backend',
                severity: 'error',
                message: apiErrorMessage(error, 'Records submission failed.'),
              },
            ])
          },
        },
      )
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
        },
        onError: (error) => {
          studio.addValidationIssues([
            {
              id: `records-backend-error-${Date.now()}`,
              source: 'backend',
              severity: 'error',
              message: apiErrorMessage(error, 'Records submission failed.'),
            },
          ])
        },
      },
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

  const completedStepIds = new Set([
    ...(activeKnowledgeBaseId ? (['knowledge-base'] as const) : []),
    ...(studio.sourceType ? (['source'] as const) : []),
    ...(studio.pendingFiles.length > 0 || studio.parsedRows.length > 0 ? (['preview'] as const) : []),
    ...(currentIssues.length === 0 ? (['validate'] as const) : []),
    ...(studio.receipts.length > 0 ? (['submit'] as const) : []),
  ])
  const errorStepIds = new Set(currentIssues.length > 0 ? (['validate'] as const) : [])

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
              activeKnowledgeBaseId={activeKnowledgeBaseId}
              createDescription={knowledgeBaseDescription}
              createDisabled={createKnowledgeBaseMutation.isPending}
              createName={knowledgeBaseName}
              deleteDisabled={deleteKnowledgeBaseMutation.isPending}
              knowledgeBases={knowledgeBases}
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
            />
          </Card>

          <Card>
            <SourceTypeStep
              selectedSourceType={studio.sourceType}
              onChange={(sourceType) => {
                studio.setSourceType(sourceType)
                studio.setCurrentStep('preview')
              }}
            />
          </Card>

          {studio.sourceType === 'documents' ? (
            <Card>
              <DocumentSourcePanel
                files={studio.pendingFiles}
                onFilesChange={(files) => {
                  studio.setPendingFiles(files)
                  studio.setValidationIssues([])
                  studio.setCurrentStep('validate')
                }}
              />
            </Card>
          ) : null}

          {studio.sourceType === 'records' ? (
            <Card>
              <RecordsSourcePanel
                feeds={feeds}
                issues={recordIssues}
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
            </Card>
          ) : null}

          <Card>
            <ValidationPanel issues={currentIssues} />
          </Card>

          <Card>
            <SubmitPanel
              canSubmitDocuments={
                studio.sourceType === 'documents' &&
                studio.pendingFiles.length > 0 &&
                documentIssues.every((issue) => issue.severity !== 'error')
              }
              canSubmitRecords={
                studio.sourceType === 'records' &&
                selectedFeed !== null &&
                (selectedFeed.source !== 'file_upload' || studio.pendingRecordFile !== null) &&
                studio.parsedRows.length > 0 &&
                recordIssues.every((issue) => issue.severity !== 'error')
              }
              documentPending={uploadMutation.isPending}
              recordsPending={pushRecordsMutation.isPending || uploadRecordFileMutation.isPending}
              onSubmitDocuments={submitDocuments}
              onSubmitRecords={submitRecords}
            />
          </Card>
        </div>

        <aside className="ingestion-studio-context" aria-label="Ingestion context">
          <Card>
            <SelectedKnowledgeBaseSummary knowledgeBase={knowledgeBase} />
          </Card>

          <Card>
            <RunTimeline
              receipts={studio.receipts}
              workflows={workflowsQuery.data?.items ?? []}
            />
          </Card>

          <Card>
            <DocumentInventory
              activeDocumentId={activeDocumentId}
              deleteDisabled={deleteDocumentMutation.isPending}
              documents={documents}
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

function SelectedKnowledgeBaseSummary({
  knowledgeBase,
}: {
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

  return (
    <section className="ingestion-studio-summary" aria-labelledby="selected-kb-title">
      <div className="metric-row">
        <div>
          <strong id="selected-kb-title">{knowledgeBase.name}</strong>
          <p className="page-copy-block">{knowledgeBase.description}</p>
        </div>
        <Chip label={knowledgeBase.status} tone={toneForKnowledgeBaseStatus(knowledgeBase.status)} />
      </div>

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
    size_bytes: number | null
    status: string
    created_at: string
  }>
  onDeleteDocument: (documentId: string) => void
  onSelectDocument: (documentId: string) => void
}

function DocumentInventory({
  activeDocumentId,
  deleteDisabled,
  documents,
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
              </span>
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
    </section>
  )
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
