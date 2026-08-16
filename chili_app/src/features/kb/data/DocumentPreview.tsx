import type { KnowledgeBaseDocumentPreviewResponse } from '../../../api/contracts'
import { Chip } from '../../../components/ui/Chip'
import { EmptyState } from '../../../components/ui/EmptyState'
import { ErrorState } from '../../../components/ui/ErrorState'
import { LoadingState } from '../../../components/ui/LoadingState'
import { countLabel } from '../../../utils/countLabel'

type DocumentPreviewProps = {
  documentSelected: boolean
  /** With no documents at all, the inventory has already said so. */
  hasDocuments: boolean
  preview: KnowledgeBaseDocumentPreviewResponse | null
  loading: boolean
  error: boolean
}

export function DocumentPreview({
  documentSelected,
  hasDocuments,
  preview,
  loading,
  error,
}: DocumentPreviewProps) {
  if (!hasDocuments) {
    return null
  }

  // With no documents at all, the inventory's empty state has already said so;
  // a second "no document selected" and a third "no runs yet" made one screen
  // state the same fact three times (UXA-305). There is nothing to preview
  // until something has been ingested.
  return (
    <section className="ingestion-document-preview" aria-labelledby="document-preview-title">
      <div className="metric-row">
        <strong id="document-preview-title">Document preview</strong>
        {preview?.truncated ? <Chip label="Truncated" tone="warning" /> : null}
      </div>

      {!documentSelected ? (
        <EmptyState
          title="No document selected"
          description="Select a document in inventory to review its preview."
        />
      ) : loading ? (
        <LoadingState label="Loading document preview" />
      ) : error ? (
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
  )
}
