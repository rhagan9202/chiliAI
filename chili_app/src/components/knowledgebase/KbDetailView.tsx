import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useKnowledgeBase } from '../../hooks/useKnowledgeBases'
import {
  useDeleteDocument,
  useKnowledgeBaseDocuments,
  useUploadDocument,
} from '../../hooks/useKnowledgeBaseDocuments'
import type { DocumentSummary } from '../../types/api'
import { ConfirmDialog } from '../common/ConfirmDialog'
import { Skeleton } from '../common/Skeleton'
import { showToast } from '../common/toastStore'
import { DocumentTable } from './DocumentTable'
import { DropZone } from './DropZone'
import { StatusBadge } from './StatusBadge'
import { UploadProgress } from './UploadProgress'

interface ActiveUpload {
  filename: string
  percent: number
}

export function KbDetailView(): React.ReactElement {
  const { kbId } = useParams<{ kbId: string }>()
  const { data: kb, isLoading: kbLoading, error: kbError } =
    useKnowledgeBase(kbId)
  const {
    data: docs,
    isLoading: docsLoading,
    error: docsError,
  } = useKnowledgeBaseDocuments(kbId)

  const uploadMutation = useUploadDocument(kbId ?? '')
  const deleteMutation = useDeleteDocument(kbId ?? '')

  const [activeUpload, setActiveUpload] = useState<ActiveUpload | null>(null)
  const [pendingDelete, setPendingDelete] = useState<DocumentSummary | null>(
    null,
  )

  if (!kbId) {
    return <p>Missing knowledge base id.</p>
  }

  const handleFile = (file: File): void => {
    setActiveUpload({ filename: file.name, percent: 0 })
    uploadMutation.mutate(
      {
        file,
        onProgress: (percent) =>
          setActiveUpload((current) =>
            current ? { ...current, percent } : current,
          ),
      },
      {
        onSuccess: () => {
          showToast('success', `Uploaded ${file.name}.`)
          setActiveUpload(null)
        },
        onError: (err) => {
          showToast('error', `Upload failed: ${err.message}`)
          setActiveUpload(null)
        },
      },
    )
  }

  const confirmDelete = (): void => {
    if (!pendingDelete) return
    const doc = pendingDelete
    deleteMutation.mutate(doc.id, {
      onSuccess: () => {
        showToast('success', `Deleted ${doc.filename}.`)
        setPendingDelete(null)
      },
      onError: (err) => {
        showToast('error', `Delete failed: ${err.message}`)
        setPendingDelete(null)
      },
    })
  }

  return (
    <section>
      <p style={{ marginTop: 0 }}>
        <Link to="/knowledgebases">← All knowledge bases</Link>
      </p>
      {kbLoading ? (
        <Skeleton width={200} height={28} />
      ) : kbError ? (
        <p style={{ color: '#b91c1c' }}>
          Failed to load knowledge base: {kbError.message}
        </p>
      ) : kb ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <h1 style={{ margin: 0 }}>{kb.name}</h1>
          <StatusBadge status={kb.status} />
          <span style={{ fontSize: 13, color: 'var(--text, #6b6375)' }}>
            {kb.document_count} document(s)
          </span>
        </div>
      ) : null}
      {kb?.description ? (
        <p style={{ color: 'var(--text, #6b6375)' }}>{kb.description}</p>
      ) : null}

      <div style={{ marginTop: 24 }}>
        <DropZone
          onFile={handleFile}
          disabled={uploadMutation.isPending}
          onValidationError={(reason) => showToast('warning', reason)}
        />
        {activeUpload ? (
          <UploadProgress
            filename={activeUpload.filename}
            percent={activeUpload.percent}
          />
        ) : null}
      </div>

      <div style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: 16, margin: '0 0 12px' }}>Documents</h2>
        {docsLoading ? (
          <Skeleton width="100%" height={120} />
        ) : docsError ? (
          <p style={{ color: '#b91c1c' }}>
            Failed to load documents: {docsError.message}
          </p>
        ) : (
          <DocumentTable
            documents={docs?.items ?? []}
            onDelete={(doc) => setPendingDelete(doc)}
          />
        )}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete document"
        message={
          pendingDelete
            ? `Are you sure you want to delete "${pendingDelete.filename}"? This cannot be undone.`
            : ''
        }
        confirmLabel={deleteMutation.isPending ? 'Deleting…' : 'Delete'}
        destructive
        onCancel={() => setPendingDelete(null)}
        onConfirm={confirmDelete}
      />
    </section>
  )
}
