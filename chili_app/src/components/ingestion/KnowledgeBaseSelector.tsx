import type { FormEvent } from 'react'

import type { KnowledgeBaseStatus, KnowledgeBaseSummaryResponse } from '../../api/contracts'
import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import './ingestion.css'

type KnowledgeBaseSelectorProps = {
  activeKnowledgeBaseId: string | null
  createDescription: string
  createDisabled: boolean
  createName: string
  deleteDisabled: boolean
  knowledgeBases: KnowledgeBaseSummaryResponse[]
  onCreateDescriptionChange: (value: string) => void
  onCreateNameChange: (value: string) => void
  onCreateSubmit: () => void
  onDelete: (knowledgeBaseId: string) => void
  onSelect: (knowledgeBaseId: string) => void
}

function countLabel(count: number) {
  return `${count} ${count === 1 ? 'knowledge base' : 'knowledge bases'}`
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
  activeKnowledgeBaseId,
  createDescription,
  createDisabled,
  createName,
  deleteDisabled,
  knowledgeBases,
  onCreateDescriptionChange,
  onCreateNameChange,
  onCreateSubmit,
  onDelete,
  onSelect,
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
        <h2 id="ingestion-kb-selector-title" className="ingestion-kb-selector__title">
          Knowledge bases
        </h2>
        <Chip label={countLabel(knowledgeBases.length)} tone="info" />
      </div>

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
                    label={knowledgeBase.status}
                    tone={toneForKnowledgeBaseStatus(knowledgeBase.status)}
                  />
                  <Chip label={`${knowledgeBase.document_count} docs`} tone="default" />
                  <Chip label={`${knowledgeBase.entity_count} entities`} tone="network" />
                </span>
              </button>
            )
          })}
        </div>
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
