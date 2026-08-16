import { useState } from 'react'
import type { FormEvent } from 'react'

import { useCreateKnowledgeBase } from '../../../api/knowledgebases'
// Reuses `KnowledgeBaseSelector`'s field/label classnames until the cutover
// that deletes it retires this stylesheet too.
import '../../../components/ingestion/ingestion.css'

type CreateKnowledgeBasePanelProps = {
  onCreated: (knowledgeBaseId: string) => void
}

/**
 * The create affordance, folded into `<details>` rather than sitting open on
 * the page permanently: creating a knowledge base is rarer than browsing one.
 */
export function CreateKnowledgeBasePanel({ onCreated }: CreateKnowledgeBasePanelProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const createKnowledgeBase = useCreateKnowledgeBase()

  const isCreateDisabled = createKnowledgeBase.isPending || name.trim().length === 0

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (isCreateDisabled) {
      return
    }

    createKnowledgeBase.mutate(
      { name, description },
      {
        onSuccess: (created) => {
          setName('')
          setDescription('')
          onCreated(created.id)
        },
      },
    )
  }

  return (
    <details className="kb-library__create">
      <summary className="page-button page-button--primary">New knowledge base</summary>
      <form onSubmit={handleSubmit}>
        <label className="ingestion-kb-selector__field">
          <span className="ingestion-kb-selector__label">Knowledge base name</span>
          <input
            className="page-input"
            onChange={(event) => setName(event.target.value)}
            placeholder="Name"
            value={name}
          />
        </label>
        <label className="ingestion-kb-selector__field">
          <span className="ingestion-kb-selector__label">Description</span>
          <textarea
            className="page-textarea"
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Describe the corpus, policy scope, or intended analyst workflow"
            value={description}
          />
        </label>
        <button className="page-button" disabled={isCreateDisabled} type="submit">
          {createKnowledgeBase.isPending ? 'Creating...' : 'Create knowledge base'}
        </button>
      </form>
    </details>
  )
}
