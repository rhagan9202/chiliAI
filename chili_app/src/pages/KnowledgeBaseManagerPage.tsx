import { useState } from 'react'

import {
  useCreateKnowledgeBase,
  useDeleteKnowledgeBase,
  useDeleteKnowledgeBaseDocument,
  useKnowledgeBase,
  useKnowledgeBaseDocuments,
  useKnowledgeBases,
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
  const createKnowledgeBaseMutation = useCreateKnowledgeBase()
  const deleteKnowledgeBaseMutation = useDeleteKnowledgeBase()
  const uploadMutation = useUploadKnowledgeBaseDocuments(activeKnowledgeBaseId)
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

  if (knowledgeBases.length === 0) {
    return (
      <section className="page-grid">
        <SectionHeader
          actions={<Chip label="0 knowledge bases" tone="info" />}
          eyebrow="Ingestion control"
          subtitle="Create a knowledge base before uploading documents or running graph ingestion."
          title="Knowledge Base Manager"
        />
        <Card>
          <EmptyState
            description="Create a corpus for policy, claims, or reference documents to begin ingestion."
            title="No knowledge bases yet"
          />
          <CreateKnowledgeBaseForm
            description={knowledgeBaseDescription}
            disabled={createKnowledgeBaseMutation.isPending}
            name={knowledgeBaseName}
            onDescriptionChange={setKnowledgeBaseDescription}
            onNameChange={setKnowledgeBaseName}
            onSubmit={() => {
              createKnowledgeBaseMutation.mutate(
                {
                  name: knowledgeBaseName.trim(),
                  description: knowledgeBaseDescription.trim(),
                },
                {
                  onSuccess: (created) => {
                    setSelectedKnowledgeBaseId(created.id)
                    setKnowledgeBaseName('')
                    setKnowledgeBaseDescription('')
                  },
                },
              )
            }}
          />
        </Card>
      </section>
    )
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

  const knowledgeBase = knowledgeBaseDetailQuery.data

  const isSubmittingCreate = createKnowledgeBaseMutation.isPending
  const isSubmittingUpload = uploadMutation.isPending

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label={`${knowledgeBases.length} knowledge bases`} tone="info" />}
        eyebrow="Ingestion control"
        subtitle="Manage live knowledge base metadata, document inventory, and upload registration against the backend API."
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

            <CreateKnowledgeBaseForm
              description={knowledgeBaseDescription}
              disabled={isSubmittingCreate}
              name={knowledgeBaseName}
              onDescriptionChange={setKnowledgeBaseDescription}
              onNameChange={setKnowledgeBaseName}
              onSubmit={() => {
                createKnowledgeBaseMutation.mutate(
                  {
                    name: knowledgeBaseName.trim(),
                    description: knowledgeBaseDescription.trim(),
                  },
                  {
                    onSuccess: (created) => {
                      setSelectedKnowledgeBaseId(created.id)
                      setKnowledgeBaseName('')
                      setKnowledgeBaseDescription('')
                    },
                  },
                )
              }}
            />
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
                  <strong>{formatTimestamp(knowledgeBase.created_at)}</strong>
                </div>
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
                          {formatFileSize(document.size_bytes)} • {formatTimestamp(document.created_at)}
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
                <strong>Selected document</strong>
                {activeDocumentId ? (
                  <div className="page-actions-inline">
                    <Chip label={documents.find((document) => document.id === activeDocumentId)?.filename ?? activeDocumentId} tone="default" />
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
              <EmptyState
                description={
                  activeDocumentId
                    ? 'Per-document timelines are not exposed by the current API. Use document status in the inventory until timeline projection is available.'
                    : 'Select a document to inspect its current registration status.'
                }
                title={activeDocumentId ? 'Timeline unavailable' : 'No document selected'}
              />
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
  if (status === 'validated') {
    return 'success' as const
  }
  if (status === 'failed') {
    return 'danger' as const
  }
  return 'warning' as const
}

interface CreateKnowledgeBaseFormProps {
  description: string
  disabled: boolean
  name: string
  onDescriptionChange: (value: string) => void
  onNameChange: (value: string) => void
  onSubmit: () => void
}

function CreateKnowledgeBaseForm({
  description,
  disabled,
  name,
  onDescriptionChange,
  onNameChange,
  onSubmit,
}: CreateKnowledgeBaseFormProps) {
  return (
    <div className="knowledge-base-form">
      <strong>Create knowledge base</strong>
      <input
        className="page-input"
        onChange={(event) => onNameChange(event.target.value)}
        placeholder="Name"
        value={name}
      />
      <textarea
        className="page-textarea"
        onChange={(event) => onDescriptionChange(event.target.value)}
        placeholder="Describe the corpus, policy scope, or intended analyst workflow"
        value={description}
      />
      <button
        className="page-button"
        disabled={disabled || name.trim().length === 0 || description.trim().length === 0}
        onClick={onSubmit}
        type="button"
      >
        {disabled ? 'Creating…' : 'Create knowledge base'}
      </button>
    </div>
  )
}
