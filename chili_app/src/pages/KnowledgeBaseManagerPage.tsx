import { useState } from 'react'

import {
  useCreateKnowledgeBase,
  useDeleteKnowledgeBase,
  useDeleteKnowledgeBaseDocument,
  useKnowledgeBase,
  useKnowledgeBaseDocumentStatus,
  useKnowledgeBaseDocuments,
  useKnowledgeBases,
  useRebuildKnowledgeBase,
  useUploadKnowledgeBaseDocuments,
} from '../api/knowledgebases'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

export function KnowledgeBaseManagerPage() {
  const knowledgeBasesQuery = useKnowledgeBases()
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<string | null>(null)
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null)
  const [knowledgeBaseName, setKnowledgeBaseName] = useState('')
  const [knowledgeBaseDescription, setKnowledgeBaseDescription] = useState('')
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const activeKnowledgeBaseId = knowledgeBases.some((item) => item.id === selectedKnowledgeBaseId)
    ? selectedKnowledgeBaseId
    : knowledgeBases[0]?.id ?? null
  const knowledgeBaseDetailQuery = useKnowledgeBase(activeKnowledgeBaseId)
  const documentsQuery = useKnowledgeBaseDocuments(activeKnowledgeBaseId)
  const documents = documentsQuery.data?.items ?? []
  const activeDocumentId = documents.some((document) => document.id === selectedDocumentId)
    ? selectedDocumentId
    : documents[0]?.id ?? null
  const documentStatusQuery = useKnowledgeBaseDocumentStatus(activeKnowledgeBaseId, activeDocumentId)
  const createKnowledgeBaseMutation = useCreateKnowledgeBase()
  const deleteKnowledgeBaseMutation = useDeleteKnowledgeBase()
  const uploadMutation = useUploadKnowledgeBaseDocuments(activeKnowledgeBaseId)
  const rebuildMutation = useRebuildKnowledgeBase(activeKnowledgeBaseId)
  const deleteDocumentMutation = useDeleteKnowledgeBaseDocument(activeKnowledgeBaseId)

  if (knowledgeBasesQuery.isLoading) {
    return <LoadingState label="Loading knowledge base inventory" />
  }

  if (knowledgeBasesQuery.isError) {
    return <ErrorState description="Knowledge base inventory could not be loaded from the API." />
  }

  if (!knowledgeBasesQuery.data) {
    return <LoadingState label="Waiting for knowledge base inventory" />
  }

  if (knowledgeBaseDetailQuery.isLoading || documentsQuery.isLoading) {
    return <LoadingState label="Loading knowledge base detail" />
  }

  if (knowledgeBaseDetailQuery.isError || documentsQuery.isError) {
    return <ErrorState description="Knowledge base detail could not be loaded from the API." />
  }

  if (!knowledgeBaseDetailQuery.data || !documentsQuery.data) {
    return <LoadingState label="Waiting for knowledge base detail" />
  }

  const knowledgeBase = knowledgeBaseDetailQuery.data.knowledge_base

  const documentStatus = documentStatusQuery.data
  const isSubmittingCreate = createKnowledgeBaseMutation.isPending
  const isSubmittingUpload = uploadMutation.isPending
  const isRebuilding = rebuildMutation.isPending

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label={`${knowledgeBases.length} knowledge bases`} tone="info" />}
        eyebrow="Ingestion control"
        subtitle="Phase 6 replaces the placeholder with live knowledge base metadata, document inventory, status timelines, upload registration, and rebuild controls."
        title="Knowledge Base Manager"
      />

      <div className="knowledge-base-layout">
        <Card>
          <div className="metric-stack">
            <div className="metric-row">
              <strong>Knowledge bases</strong>
              <Chip label={knowledgeBase.status} tone={toneForKnowledgeBaseStatus(knowledgeBase.status)} />
            </div>

            {knowledgeBases.map((item) => (
              <button
                className={
                  activeKnowledgeBaseId === item.id
                    ? 'page-list-item page-list-item--active'
                    : 'page-list-item'
                }
                key={item.id}
                onClick={() => {
                  setSelectedKnowledgeBaseId(item.id)
                  setSelectedDocumentId(null)
                  setPendingFiles([])
                }}
                type="button"
              >
                <strong>{item.name}</strong>
                <span className="metric-row__label">{item.description}</span>
                <div className="alert-row-card__meta">
                  <Chip label={`${item.document_count} docs`} tone="default" />
                  <Chip label={`${item.entity_count} entities`} tone="network" />
                </div>
              </button>
            ))}

            <div className="knowledge-base-form">
              <strong>Create knowledge base</strong>
              <input
                className="page-input"
                onChange={(event) => setKnowledgeBaseName(event.target.value)}
                placeholder="Name"
                value={knowledgeBaseName}
              />
              <textarea
                className="page-textarea"
                onChange={(event) => setKnowledgeBaseDescription(event.target.value)}
                placeholder="Describe the corpus, policy scope, or intended analyst workflow"
                value={knowledgeBaseDescription}
              />
              <button
                className="page-button"
                disabled={
                  isSubmittingCreate ||
                  knowledgeBaseName.trim().length === 0 ||
                  knowledgeBaseDescription.trim().length === 0
                }
                onClick={() => {
                  createKnowledgeBaseMutation.mutate(
                    {
                      name: knowledgeBaseName.trim(),
                      description: knowledgeBaseDescription.trim(),
                    },
                    {
                      onSuccess: (created) => {
                        setSelectedKnowledgeBaseId(created.knowledge_base.id)
                        setKnowledgeBaseName('')
                        setKnowledgeBaseDescription('')
                      },
                    },
                  )
                }}
                type="button"
              >
                {isSubmittingCreate ? 'Creating…' : 'Create knowledge base'}
              </button>
            </div>
          </div>
        </Card>

        <div className="knowledge-base-main">
          <Card>
            <div className="metric-stack">
              <div className="metric-row">
                <div>
                  <strong>{knowledgeBase.name}</strong>
                  <p className="page-copy-block">{knowledgeBase.description}</p>
                </div>
                <div className="page-actions-inline">
                  <button
                    className="page-button"
                    disabled={isRebuilding}
                    onClick={() => rebuildMutation.mutate()}
                    type="button"
                  >
                    {isRebuilding ? 'Queueing rebuild…' : 'Rebuild index'}
                  </button>
                  <button
                    className="page-button page-button--secondary"
                    disabled={deleteKnowledgeBaseMutation.isPending}
                    onClick={() =>
                      deleteKnowledgeBaseMutation.mutate(activeKnowledgeBaseId ?? '', {
                        onSuccess: () => {
                          setSelectedKnowledgeBaseId(null)
                          setSelectedDocumentId(null)
                        },
                      })
                    }
                    type="button"
                  >
                    Delete knowledge base
                  </button>
                </div>
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
                  <span className="metric-row__label">Last ingest</span>
                  <strong>{formatTimestamp(knowledgeBase.last_ingested_at)}</strong>
                </div>
              </div>

              <div className="knowledge-base-workflows">
                <strong>Recent workflows</strong>
                {knowledgeBaseDetailQuery.data.recent_workflows.map((workflow) => (
                  <div className="metric-row" key={workflow.id}>
                    <span>{workflow.workflow_type.replace('_', ' ')}</span>
                    <div className="alert-row-card__meta">
                      <Chip label={workflow.status} tone={toneForWorkflowStatus(workflow.status)} />
                      <Chip label={workflow.current_step.replace(/_/g, ' ')} tone="default" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          <div className="knowledge-base-detail-grid">
            <Card>
              <div className="metric-stack">
                <div className="metric-row">
                  <strong>Document upload</strong>
                  <Chip label={pendingFiles.length > 0 ? `${pendingFiles.length} selected` : 'No files'} tone="info" />
                </div>
                <input
                  className="page-input page-input--file"
                  multiple
                  onChange={(event) => setPendingFiles(Array.from(event.target.files ?? []))}
                  type="file"
                />
                {pendingFiles.length > 0 ? (
                  <div className="alert-row-card__meta">
                    {pendingFiles.map((file) => (
                      <Chip key={`${file.name}-${file.size}`} label={file.name} tone="default" />
                    ))}
                  </div>
                ) : null}
                <button
                  className="page-button"
                  disabled={isSubmittingUpload || pendingFiles.length === 0}
                  onClick={() => {
                    uploadMutation.mutate(pendingFiles, {
                      onSuccess: () => {
                        setPendingFiles([])
                      },
                    })
                  }}
                  type="button"
                >
                  {isSubmittingUpload ? 'Registering documents…' : 'Upload documents'}
                </button>
              </div>
            </Card>

            <Card>
              <div className="metric-stack">
                <div className="metric-row">
                  <strong>Document inventory</strong>
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
                        onClick={() => setSelectedDocumentId(document.id)}
                        type="button"
                      >
                        <strong>{document.filename}</strong>
                        <span className="metric-row__label">
                          {formatFileSize(document.size_bytes)} • {formatTimestamp(document.uploaded_at)}
                        </span>
                        <div className="alert-row-card__meta">
                          <Chip label={document.status} tone={toneForDocumentStatus(document.status)} />
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <EmptyState description="Register policy, claims, or reference documents to start ingestion." title="No documents yet" />
                )}
              </div>
            </Card>
          </div>

          <Card>
            <div className="metric-stack">
              <div className="metric-row">
                <strong>Ingestion status timeline</strong>
                {documentStatus?.document ? (
                  <div className="page-actions-inline">
                    <Chip label={documentStatus.document.filename} tone="default" />
                    <button
                      className="page-button page-button--secondary"
                      disabled={deleteDocumentMutation.isPending}
                      onClick={() => {
                        if (!activeDocumentId) {
                          return
                        }
                        deleteDocumentMutation.mutate(activeDocumentId, {
                          onSuccess: () => setSelectedDocumentId(null),
                        })
                      }}
                      type="button"
                    >
                      Remove document
                    </button>
                  </div>
                ) : null}
              </div>

              {documentStatusQuery.isLoading ? (
                <LoadingState label="Loading document timeline" />
              ) : documentStatusQuery.isError ? (
                <ErrorState description="Document timeline could not be loaded from the API." />
              ) : documentStatus ? (
                <div className="knowledge-base-timeline">
                  {documentStatus.timeline.map((entry) => (
                    <div className="knowledge-base-timeline__item" key={`${entry.stage}-${entry.updated_at}`}>
                      <div className="metric-row">
                        <strong>{entry.stage.replace(/_/g, ' ')}</strong>
                        <Chip label={entry.status} tone={toneForTimelineStatus(entry.status)} />
                      </div>
                      <span className="metric-row__label">{formatTimestamp(entry.updated_at)}</span>
                      <p className="page-copy-block">{entry.message}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState description="Select a document to inspect the ingest stages and current parser/indexing state." title="No document selected" />
              )}
            </div>
          </Card>
        </div>
      </div>
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

function toneForKnowledgeBaseStatus(status: 'ready' | 'indexing' | 'rebuilding' | 'error') {
  switch (status) {
    case 'ready':
      return 'success' as const
    case 'indexing':
    case 'rebuilding':
      return 'warning' as const
    case 'error':
      return 'danger' as const
  }
}

function toneForDocumentStatus(status: string) {
  if (status === 'validated') {
    return 'success' as const
  }
  if (status === 'failed') {
    return 'danger' as const
  }
  return 'warning' as const
}

function toneForTimelineStatus(status: 'pending' | 'running' | 'completed' | 'failed') {
  switch (status) {
    case 'completed':
      return 'success' as const
    case 'failed':
      return 'danger' as const
    case 'running':
      return 'info' as const
    case 'pending':
      return 'default' as const
  }
}

function toneForWorkflowStatus(status: 'queued' | 'running' | 'completed' | 'failed') {
  switch (status) {
    case 'completed':
      return 'success' as const
    case 'failed':
      return 'danger' as const
    case 'running':
      return 'info' as const
    case 'queued':
      return 'warning' as const
  }
}