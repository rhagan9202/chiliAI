import type { CSSProperties } from 'react'

export interface SkeletonProps {
  width?: number | string
  height?: number | string
  radius?: number | string
  ariaLabel?: string
}

export function Skeleton({
  width = '100%',
  height = 16,
  radius = 4,
  ariaLabel = 'Loading',
}: SkeletonProps): React.ReactElement {
  const style: CSSProperties = {
    display: 'inline-block',
    width,
    height,
    borderRadius: radius,
    background:
      'linear-gradient(90deg, rgba(0,0,0,0.06) 25%, rgba(0,0,0,0.12) 37%, rgba(0,0,0,0.06) 63%)',
    backgroundSize: '400% 100%',
    animation: 'chili-skeleton-pulse 1.4s ease infinite',
  }
  return (
    <>
      <span
        role="status"
        aria-label={ariaLabel}
        aria-live="polite"
        style={style}
      />
      <style>
        {`@keyframes chili-skeleton-pulse {
            0% { background-position: 100% 50%; }
            100% { background-position: 0 50%; }
          }`}
      </style>
    </>
  )
}
