import { useState } from 'react'
import type { FormEvent } from 'react'

import { useCreateKnowledgeBase } from '../../hooks/useKnowledgeBases'
import { showToast } from '../common/toastStore'

export interface CreateKbFormProps {
  open: boolean
  onClose: () => void
  onCreated?: (id: string) => void
}

export function CreateKbForm({
  open,
  onClose,
  onCreated,
}: CreateKbFormProps): React.ReactElement | null {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const mutation = useCreateKnowledgeBase()

  if (!open) return null

  const handleClose = (): void => {
    if (mutation.isPending) return
    setName('')
    setDescription('')
    mutation.reset()
    onClose()
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault()
    if (name.trim().length === 0) return
    mutation.mutate(
      { name: name.trim(), description: description.trim() },
      {
        onSuccess: (kb) => {
          showToast('success', `Knowledge base "${kb.name}" created.`)
          setName('')
          setDescription('')
          onCreated?.(kb.id)
          onClose()
        },
        onError: (err) => {
          showToast(
            'error',
            `Failed to create knowledge base: ${err.message}`,
          )
        },
      },
    )
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-kb-title"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
        padding: 16,
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) handleClose()
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          background: 'var(--bg, #fff)',
          borderRadius: 8,
          padding: 24,
          minWidth: 320,
          maxWidth: 480,
          width: '100%',
          boxShadow: '0 12px 32px rgba(0, 0, 0, 0.18)',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        <h2 id="create-kb-title" style={{ margin: 0, fontSize: 18 }}>
          Create Knowledge Base
        </h2>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 500 }}>Name</span>
          <input
            type="text"
            required
            minLength={1}
            maxLength={200}
            value={name}
            onChange={(event) => setName(event.target.value)}
            disabled={mutation.isPending}
            style={{
              padding: '8px 10px',
              borderRadius: 4,
              border: '1px solid var(--border, #e5e4e7)',
              fontSize: 14,
            }}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 500 }}>Description</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            disabled={mutation.isPending}
            rows={3}
            maxLength={2000}
            style={{
              padding: '8px 10px',
              borderRadius: 4,
              border: '1px solid var(--border, #e5e4e7)',
              fontSize: 14,
              resize: 'vertical',
            }}
          />
        </label>
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
            marginTop: 8,
          }}
        >
          <button
            type="button"
            onClick={handleClose}
            disabled={mutation.isPending}
            style={{
              padding: '8px 14px',
              borderRadius: 4,
              border: '1px solid var(--border, #e5e4e7)',
              background: 'transparent',
              cursor: mutation.isPending ? 'not-allowed' : 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={mutation.isPending || name.trim().length === 0}
            style={{
              padding: '8px 14px',
              borderRadius: 4,
              border: 'none',
              background: 'var(--accent, #aa3bff)',
              color: '#fff',
              cursor:
                mutation.isPending || name.trim().length === 0
                  ? 'not-allowed'
                  : 'pointer',
            }}
          >
            {mutation.isPending ? 'Creating…' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  )
}
