import type { FormEvent } from 'react'

import type { KnowledgeBaseStatus, KnowledgeBaseSummaryResponse } from '../../api/contracts'
import { countLabel } from '../../utils/countLabel'
import { knowledgeBaseStatusLabel } from '../../utils/knowledgeBaseStatus'
import { KbDomainBadge } from '../knowledgebase/KbDomainBadge'
import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import './ingestion.css'

type KnowledgeBaseSelectorProps = {
  /** `domain.name` of the active domain config; enables the warn-only domain badge. */
  activeDomainName?: string | null
  activeKnowledgeBaseId: string | null
  createDescription: string
  createDisabled: boolean
  createName: string
  deleteDisabled: boolean
  /**
   * Number of knowledge bases from other domains excluded from `knowledgeBases`
   * when domain scoping is active. When > 0 a show-all-domains toggle renders.
   */
  hiddenDomainCount?: number
  knowledgeBases: KnowledgeBaseSummaryResponse[]
  onCreateDescriptionChange: (value: string) => void
  onCreateNameChange: (value: string) => void
  onCreateSubmit: () => void
  onDelete: (knowledgeBaseId: string) => void
  onSelect: (knowledgeBaseId: string) => void
  onToggleShowAllDomains?: () => void
  /** Whether the list currently includes knowledge bases from all domains. */
  showAllDomains?: boolean
}

function toneForKnowledgeBaseStatus(status: KnowledgeBaseStatus) {
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

export function KnowledgeBaseSelector({
  activeDomainName = null,
  activeKnowledgeBaseId,
  createDescription,
  createDisabled,
  createName,
  deleteDisabled,
  hiddenDomainCount = 0,
  knowledgeBases,
  onCreateDescriptionChange,
  onCreateNameChange,
  onCreateSubmit,
  onDelete,
  onSelect,
  onToggleShowAllDomains,
  showAllDomains = false,
}: KnowledgeBaseSelectorProps) {
  const isCreateDisabled = createDisabled || createName.trim().length === 0

  function handleCreateSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!isCreateDisabled) {
      onCreateSubmit()
    }
  }

  return (
    <section className="ingestion-kb-selector" aria-labelledby="ingestion-kb-selector-title">
      <div className="ingestion-kb-selector__header">
        {/* Named for its job, not its contents: the page itself is already
            called Knowledge Bases, and two headings by that name are two
            things with one name. */}
        <h2 id="ingestion-kb-selector-title" className="ingestion-kb-selector__title">
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
        <div className="ingestion-kb-list">
          {knowledgeBases.map((knowledgeBase) => {
            const isActive = activeKnowledgeBaseId === knowledgeBase.id

            return (
              <button
                aria-pressed={isActive}
                className={[
                  'page-list-item',
                  'ingestion-kb-list__item',
                  isActive ? 'page-list-item--active' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                key={knowledgeBase.id}
                onClick={() => onSelect(knowledgeBase.id)}
                type="button"
              >
                <span className="ingestion-kb-list__name">{knowledgeBase.name}</span>
                <span className="ingestion-kb-list__description">
                  {knowledgeBase.description}
                </span>
                <span className="ingestion-kb-list__meta">
                  <Chip
                    label={knowledgeBaseStatusLabel(knowledgeBase.status)}
                    tone={toneForKnowledgeBaseStatus(knowledgeBase.status)}
                  />
                  <Chip label={countLabel(knowledgeBase.document_count, 'document')} tone="default" />
                  <Chip label={countLabel(knowledgeBase.entity_count, 'entity', 'entities')} tone="network" />
                  <KbDomainBadge
                    activeDomainName={activeDomainName}
                    kbDomain={knowledgeBase.domain ?? null}
                  />
                </span>
              </button>
            )
          })}
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

      {activeKnowledgeBaseId ? (
        <button
          className="page-button page-button--secondary ingestion-kb-selector__delete"
          disabled={deleteDisabled}
          onClick={() => onDelete(activeKnowledgeBaseId)}
          type="button"
        >
          Delete selected knowledge base
        </button>
      ) : null}

      <form className="ingestion-kb-selector__form" onSubmit={handleCreateSubmit}>
        <strong>Create knowledge base</strong>
        <label className="ingestion-kb-selector__field">
          <span className="ingestion-kb-selector__label">Knowledge base name</span>
          <input
            className="page-input"
            onChange={(event) => onCreateNameChange(event.target.value)}
            placeholder="Name"
            value={createName}
          />
        </label>
        <label className="ingestion-kb-selector__field">
          <span className="ingestion-kb-selector__label">Description</span>
          <textarea
            className="page-textarea"
            onChange={(event) => onCreateDescriptionChange(event.target.value)}
            placeholder="Describe the corpus, policy scope, or intended analyst workflow"
            value={createDescription}
          />
        </label>
        <button className="page-button" disabled={isCreateDisabled} type="submit">
          {createDisabled ? 'Creating...' : 'Create knowledge base'}
        </button>
      </form>
    </section>
  )
}
