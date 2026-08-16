import { useState } from 'react'

import type { KnowledgeBaseDocumentListResponse } from '../../../api/contracts'
import { StatusChip } from '../../../components/status/StatusChip'
import { statusToken } from '../../../components/status/statusTokens'
import { formatFileSize, formatTimestamp } from '../../../components/status/formatters'
import { Chip } from '../../../components/ui/Chip'
import { EmptyState } from '../../../components/ui/EmptyState'
import { countLabel } from '../../../utils/countLabel'

/** Lifecycle states worth filtering by; the in-progress states churn too fast. */
const DOCUMENT_STATUS_FILTERS = ['all', 'validated', 'extracted_empty', 'failed'] as const

export type DocumentInventoryProps = {
  activeDocumentId: string | null
  deleteDisabled: boolean
  documents: KnowledgeBaseDocumentListResponse['items']
  statusFilter: string
  onStatusFilterChange: (status: string) => void
  onStageSource: () => void
  onDeleteDocument: (documentId: string) => void
  onSelectDocument: (documentId: string) => void
}

export function DocumentInventory({
  activeDocumentId,
  deleteDisabled,
  documents,
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
    </section>
  )
}
