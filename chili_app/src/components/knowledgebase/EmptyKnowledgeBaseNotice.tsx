import { Link } from 'react-router'

import type { KnowledgeBaseSummaryResponse } from '../../api/contracts'
import { knowledgeBaseWorkspacePath } from '../../utils/knowledgeBaseRoutes'

interface EmptyKnowledgeBaseNoticeProps {
  knowledgeBase: KnowledgeBaseSummaryResponse | null
}

/**
 * Warns before a question is asked, rather than after it returns nothing.
 *
 * A knowledge base with no documents and no entities can only answer "I don't
 * know", and neither RAG Chat nor the workbench said so — the analyst was left
 * to conclude the product was broken (UXA-305).
 */
export function EmptyKnowledgeBaseNotice({ knowledgeBase }: EmptyKnowledgeBaseNoticeProps) {
  if (knowledgeBase === null) return null
  const isEmpty = knowledgeBase.document_count === 0 && knowledgeBase.entity_count === 0
  if (!isEmpty) return null

  return (
    <div aria-label="Knowledge base warning" className="kb-empty-notice" role="status">
      <span>
        Nothing has been ingested into <strong>{knowledgeBase.name}</strong> yet, so there is
        nothing here to search.
      </span>
      <Link
        className="page-button page-button--sm page-button--primary"
        to={knowledgeBaseWorkspacePath(knowledgeBase.id, 'add')}
      >
        Add data
      </Link>
    </div>
  )
}
