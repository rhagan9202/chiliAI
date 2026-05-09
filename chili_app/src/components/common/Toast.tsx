import { useEffect } from 'react'

import {
  useToastStore,
  type ToastMessage,
  type ToastVariant,
} from './toastStore'

const AUTO_DISMISS_MS = 5_000

const variantColors: Record<ToastVariant, { bg: string; fg: string }> = {
  info: { bg: '#1f2937', fg: '#fff' },
  success: { bg: '#15803d', fg: '#fff' },
  error: { bg: '#b91c1c', fg: '#fff' },
  warning: { bg: '#b45309', fg: '#fff' },
}

interface SingleToastProps {
  toast: ToastMessage
  onDismiss: (id: string) => void
}

function SingleToast({
  toast,
  onDismiss,
}: SingleToastProps): React.ReactElement {
  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(toast.id), AUTO_DISMISS_MS)
    return () => window.clearTimeout(timer)
  }, [toast.id, onDismiss])

  const colors = variantColors[toast.variant]
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        background: colors.bg,
        color: colors.fg,
        padding: '10px 14px',
        borderRadius: 6,
        minWidth: 240,
        maxWidth: 400,
        boxShadow: '0 6px 16px rgba(0, 0, 0, 0.18)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        fontSize: 14,
      }}
    >
      <span>{toast.message}</span>
      <button
        type="button"
        aria-label="Dismiss notification"
        onClick={() => onDismiss(toast.id)}
        style={{
          background: 'transparent',
          border: 'none',
          color: colors.fg,
          cursor: 'pointer',
          fontSize: 16,
          lineHeight: 1,
        }}
      >
        ×
      </button>
    </div>
  )
}

export function ToastContainer(): React.ReactElement {
  const toasts = useToastStore((state) => state.toasts)
  const dismiss = useToastStore((state) => state.dismiss)
  return (
    <div
      aria-label="Notifications"
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      {toasts.map((toast) => (
        <SingleToast key={toast.id} toast={toast} onDismiss={dismiss} />
      ))}
    </div>
  )
}
