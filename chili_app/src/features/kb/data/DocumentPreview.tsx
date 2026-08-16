import type { KnowledgeBaseDocumentPreviewResponse } from '../../../api/contracts'
import { Chip } from '../../../components/ui/Chip'
import { EmptyState } from '../../../components/ui/EmptyState'
import { ErrorState } from '../../../components/ui/ErrorState'
import { LoadingState } from '../../../components/ui/LoadingState'
import { countLabel } from '../../../utils/countLabel'

type DocumentPreviewProps = {
  /** With no documents at all, the inventory has already said so. */
  hasDocuments: boolean
  preview: KnowledgeBaseDocumentPreviewResponse | null
  loading: boolean
  error: boolean
}

export function DocumentPreview({
  hasDocuments,
  preview,
  loading,
  error,
}: DocumentPreviewProps) {
  if (!hasDocuments) {
    return null
  }

  // With no documents at all, the inventory's empty state has already said so;
  // a second "no runs yet" made one screen state the same fact three times
  // (UXA-305). There is nothing to preview until something has been ingested.
  // `hasDocuments` also means a document is always selected here — the caller
  // (DataSection) falls back to the first row whenever the URL doesn't name
  // one, so there is no "no document selected" state to render.
  return (
    <section className="ingestion-document-preview" aria-labelledby="document-preview-title">
      <div className="metric-row">
        <strong id="document-preview-title">Document preview</strong>
        {preview?.truncated ? <Chip label="Truncated" tone="warning" /> : null}
      </div>

      {loading ? (
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
