import { useEffect, useId, useRef, useState } from 'react'

import './status.css'

type ConfirmDialogProps = {
  open: boolean
  title: string
  /** States the blast radius in concrete terms — counts, not "this action". */
  body: string
  confirmLabel: string
  /** When set, confirm stays disabled until the user types this exactly. */
  confirmTypedText?: string | null
  destructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/**
 * Confirmation for actions that destroy work.
 *
 * Deleting a knowledge base — eight documents, every entity, every run — was
 * one unguarded click, and so was removing a document. The typed-name variant
 * is reserved for the irreversible, whole-corpus case; everything else gets
 * the plain variant, because a confirmation the user learns to click through
 * protects nothing.
 */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  confirmTypedText = null,
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [typed, setTyped] = useState('')
  const cancelRef = useRef<HTMLButtonElement | null>(null)
  const titleId = useId()
  const bodyId = useId()
  const inputId = useId()

  // Reopening must not inherit the previous attempt's typing.
  useEffect(() => {
    if (open) {
      setTyped('')
      cancelRef.current?.focus()
    }
  }, [open])

  useEffect(() => {
    if (!open) {
      return
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onCancel()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, onCancel])

  if (!open) {
    return null
  }

  const requiresTyping = Boolean(confirmTypedText)
  const confirmEnabled = !requiresTyping || typed.trim() === confirmTypedText?.trim()

  return (
    <div className="confirm-dialog__overlay">
      <div
        aria-describedby={bodyId}
        aria-labelledby={titleId}
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <strong className="confirm-dialog__title" id={titleId}>
          {title}
        </strong>
        <p className="page-copy-block" id={bodyId}>
          {body}
        </p>

        {requiresTyping ? (
          <label className="confirm-dialog__field" htmlFor={inputId}>
            <span className="metric-row__label">
              Type <code>{confirmTypedText}</code> to confirm
            </span>
            <input
              className="page-input"
              id={inputId}
              onChange={(event) => setTyped(event.target.value)}
              type="text"
              value={typed}
            />
          </label>
        ) : null}

        <div className="confirm-dialog__actions">
          <button
            className="page-button page-button--secondary"
            onClick={onCancel}
            ref={cancelRef}
            type="button"
          >
            Cancel
          </button>
          <button
            className={
              destructive
                ? 'page-button page-button--primary confirm-dialog__confirm--destructive'
                : 'page-button page-button--primary'
            }
            disabled={!confirmEnabled}
            onClick={onConfirm}
            type="button"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
