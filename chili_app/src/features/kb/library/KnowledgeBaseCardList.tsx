import { Link } from 'react-router'

import type { KnowledgeBaseSummaryResponse } from '../../../api/contracts'
import { StatusChip } from '../../../components/status/StatusChip'
import { formatRelativeTime } from '../../../components/status/formatters'
import { KbDomainBadge } from '../../../components/knowledgebase/KbDomainBadge'
import { Chip } from '../../../components/ui/Chip'
import { EmptyState } from '../../../components/ui/EmptyState'
import { countLabel } from '../../../utils/countLabel'
import { knowledgeBaseWorkspacePath } from '../../../utils/knowledgeBaseRoutes'
// Reuses `KnowledgeBaseSelector`'s classnames until the cutover that deletes
// it retires this stylesheet too — see the module docstring below.
import '../../../components/ingestion/ingestion.css'
import '../kb.css'

type KnowledgeBaseCardListProps = {
  /** `domain.name` of the active domain config; enables the warn-only domain badge. */
  activeDomainName: string | null
  /**
   * Number of knowledge bases from other domains excluded from
   * `knowledgeBases` when domain scoping is active. When > 0 a show-all-domains
   * toggle renders.
   */
  hiddenDomainCount: number
  knowledgeBases: KnowledgeBaseSummaryResponse[]
  onToggleShowAllDomains: () => void
  /** Whether the list currently includes knowledge bases from all domains. */
  showAllDomains: boolean
}

/**
 * The library's browsing surface: one card per knowledge base, each a real
 * address rather than a selection button, so opening a corpus is navigation
 * (spec §1).
 */
export function KnowledgeBaseCardList({
  activeDomainName,
  hiddenDomainCount,
  knowledgeBases,
  onToggleShowAllDomains,
  showAllDomains,
}: KnowledgeBaseCardListProps) {
  return (
    <section aria-labelledby="kb-library-title" className="ingestion-kb-selector">
      <div className="ingestion-kb-selector__header">
        {/* Named for its job, not its contents: the page itself is already
            called Knowledge Bases, and two headings by that name are two
            things with one name. */}
        <h2 id="kb-library-title" className="ingestion-kb-selector__title">
          Choose a knowledge base
        </h2>
        <Chip label={countLabel(knowledgeBases.length, 'knowledge base')} tone="info" />
      </div>

      {hiddenDomainCount > 0 ? (
        <button
          aria-pressed={showAllDomains}
          className="page-button page-button--secondary ingestion-kb-selector__domain-toggle"
          data-testid="kb-show-all-domains-toggle"
          onClick={onToggleShowAllDomains}
          type="button"
        >
          {showAllDomains
            ? 'Scope to active domain'
            : `Show all domains (${hiddenDomainCount} hidden)`}
        </button>
      ) : null}

      {knowledgeBases.length > 0 ? (
        <div className="kb-library">
          {knowledgeBases.map((knowledgeBase) => (
            <Link
              className="page-list-item kb-library__card"
              key={knowledgeBase.id}
              to={knowledgeBaseWorkspacePath(knowledgeBase.id)}
            >
              <span className="kb-library__name">{knowledgeBase.name}</span>
              <span className="kb-library__description">{knowledgeBase.description}</span>
              <span className="kb-library__meta">
                <StatusChip kind="knowledge-base" status={knowledgeBase.status} />
                <Chip label={countLabel(knowledgeBase.document_count, 'document')} tone="default" />
                <Chip
                  label={countLabel(knowledgeBase.entity_count, 'entity', 'entities')}
                  tone="network"
                />
                <KbDomainBadge
                  activeDomainName={activeDomainName}
                  kbDomain={knowledgeBase.domain ?? null}
                />
              </span>
              <span className="metric-row__label">
                Last activity{' '}
                {formatRelativeTime(knowledgeBase.updated_at ?? knowledgeBase.created_at)}
              </span>
            </Link>
          ))}
        </div>
      ) : hiddenDomainCount > 0 ? (
        <EmptyState
          title="No knowledge bases in the active domain"
          description="Show all domains to view knowledge bases created under other domains, or create a new corpus."
        />
      ) : (
        <EmptyState
          title="No knowledge bases yet"
          description="Create a corpus before selecting sources for ingestion."
        />
      )}
    </section>
  )
}
