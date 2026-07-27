import type { ReactNode } from 'react'

interface ExpandableCountProps {
  label: string
  items: readonly string[]
  /** Rendered instead of the item list when the count is zero. */
  emptyHint?: string
  children?: ReactNode
}

/**
 * A summary count you can open (UXA-404).
 *
 * `/configuration` reported "Entities loaded 8" and "Configured roles 2" with
 * no way to see *which* eight or *which* two — a read-only stat dump about a
 * product whose thesis is that this configuration drives everything. A
 * `<details>` keeps the page scannable while making every figure inspectable
 * without JavaScript state or a modal.
 */
export function ExpandableCount({ label, items, emptyHint, children }: ExpandableCountProps) {
  return (
    <details className="config-count">
      <summary className="config-count__summary">
        <span className="metric-row__label">{label}</span>
        <strong>{items.length}</strong>
      </summary>
      {items.length > 0 ? (
        <ul className="config-count__items">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="page-copy-block">{emptyHint ?? 'Nothing is configured here.'}</p>
      )}
      {children}
    </details>
  )
}
