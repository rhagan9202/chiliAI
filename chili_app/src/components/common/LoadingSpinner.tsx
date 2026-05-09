import type { CSSProperties } from 'react'

export interface LoadingSpinnerProps {
  label?: string
  size?: number
}

export function LoadingSpinner({
  label = 'Loading…',
  size = 32,
}: LoadingSpinnerProps): React.ReactElement {
  const style: CSSProperties = {
    width: size,
    height: size,
    border: '3px solid rgba(0, 0, 0, 0.1)',
    borderTopColor: 'var(--accent, #aa3bff)',
    borderRadius: '50%',
    animation: 'chili-spin 0.8s linear infinite',
  }
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        padding: 24,
      }}
    >
      <div style={style} aria-hidden="true" />
      <span style={{ fontSize: 14, color: 'var(--text, #6b6375)' }}>{label}</span>
      <style>
        {`@keyframes chili-spin { to { transform: rotate(360deg); } }`}
      </style>
    </div>
  )
}
