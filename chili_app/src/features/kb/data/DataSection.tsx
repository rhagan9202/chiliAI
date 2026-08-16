import { useState } from 'react'
import { useSearchParams } from 'react-router'

import {
  useDeleteKnowledgeBaseDocument,
  useKnowledgeBaseDocumentPreview,
  useKnowledgeBaseDocuments,
} from '../../../api/knowledgebases'
import { ConfirmDialog } from '../../../components/status/ConfirmDialog'
import { Card } from '../../../components/ui/Card'
import { ErrorState } from '../../../components/ui/ErrorState'
import { LoadingState } from '../../../components/ui/LoadingState'
import { DocumentInventory } from './DocumentInventory'
import { DocumentPreview } from './DocumentPreview'

type DataSectionProps = {
  knowledgeBaseId: string
  /** Where "Stage a source" should send an analyst with nothing ingested yet. */
  onStageSource: () => void
}

/** Query-string key naming the document under the reader. */
const DOCUMENT_SEARCH_PARAM = 'document'

export function DataSection({ knowledgeBaseId, onStageSource }: DataSectionProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [statusFilter, setStatusFilter] = useState('all')
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null)

  const documentsQuery = useKnowledgeBaseDocuments(knowledgeBaseId, {
    ...(statusFilter === 'all' ? {} : { status: statusFilter }),
  })
  const deleteDocumentMutation = useDeleteKnowledgeBaseDocument(knowledgeBaseId)
  const documents = documentsQuery.data?.items ?? []

  // The focused document lives in the URL, so a citation can address one and a
  // reload keeps it open. A stale id (filtered out, or deleted) falls back to
  // the first row rather than stranding the reader on nothing.
  const requestedDocumentId = searchParams.get(DOCUMENT_SEARCH_PARAM)
  const activeDocumentId = documents.some((item) => item.id === requestedDocumentId)
    ? requestedDocumentId
    : documents[0]?.id ?? null

  const previewQuery = useKnowledgeBaseDocumentPreview(knowledgeBaseId, activeDocumentId)

  function selectDocument(documentId: string | null) {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (documentId === null) {
          next.delete(DOCUMENT_SEARCH_PARAM)
        } else {
          next.set(DOCUMENT_SEARCH_PARAM, documentId)
        }
        return next
      },
      { replace: true },
    )
  }

  if (documentsQuery.isLoading) {
    return <LoadingState label="Loading documents" />
  }

  if (documentsQuery.isError) {
    return <ErrorState description="This knowledge base's documents could not be loaded. Try again in a moment." />
  }

  return (
    <Card>
      <DocumentInventory
        activeDocumentId={activeDocumentId}
        deleteDisabled={deleteDocumentMutation.isPending}
        documents={documents}
        onDeleteDocument={(documentId) => setConfirmingDeleteId(documentId)}
        onSelectDocument={selectDocument}
        onStageSource={onStageSource}
        onStatusFilterChange={setStatusFilter}
        statusFilter={statusFilter}
      />
      <DocumentPreview
        documentSelected={activeDocumentId !== null}
        error={previewQuery.isError}
        hasDocuments={documents.length > 0}
        loading={previewQuery.isLoading}
        preview={previewQuery.data ?? null}
      />
      <ConfirmDialog
        body={`Removes ${
          documents.find((item) => item.id === confirmingDeleteId)?.filename ?? 'this document'
        } and the graph and vector artifacts built from it.`}
        confirmLabel="Remove document"
        destructive
        onCancel={() => setConfirmingDeleteId(null)}
        onConfirm={() => {
          const documentId = confirmingDeleteId
          setConfirmingDeleteId(null)
          if (!documentId) {
            return
          }
          deleteDocumentMutation.mutate(documentId, {
            onSuccess: () => selectDocument(null),
          })
        }}
        open={confirmingDeleteId !== null}
        title="Remove document"
      />
    </Card>
  )
}
