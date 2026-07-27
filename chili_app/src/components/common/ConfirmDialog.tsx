export interface ConfirmDialogProps {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps): React.ReactElement | null {
  if (!open) return null
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
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
        if (event.target === event.currentTarget) onCancel()
      }}
    >
      <div
        style={{
          background: 'var(--c-s2)',
          border: '1px solid var(--c-b1)',
          color: 'var(--c-text)',
          borderRadius: 12,
          padding: 24,
          minWidth: 320,
          maxWidth: 440,
          width: '100%',
          boxShadow: '0 12px 32px rgba(0, 0, 0, 0.5)',
        }}
      >
        <h2
          id="confirm-dialog-title"
          style={{ margin: '0 0 8px', fontSize: 18, color: 'var(--c-text)' }}
        >
          {title}
        </h2>
        <p style={{ margin: '0 0 16px', color: 'var(--c-dim)' }}>
          {message}
        </p>
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
          }}
        >
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: '8px 14px',
              borderRadius: 4,
              border: '1px solid var(--c-control-border)',
              background: 'transparent',
              color: 'var(--c-text)',
              cursor: 'pointer',
            }}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            style={{
              padding: '8px 14px',
              borderRadius: 4,
              border: 'none',
              background: destructive ? 'var(--c-red)' : 'var(--c-cyan)',
              color: destructive ? '#fff' : 'var(--c-bg)',
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
