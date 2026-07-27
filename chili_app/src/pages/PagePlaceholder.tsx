import type { ReactNode } from 'react'

type PagePlaceholderProps = {
  title: string
  eyebrow: string
  children: ReactNode
}

export function PagePlaceholder({ title, eyebrow, children }: PagePlaceholderProps) {
  return (
    <section className="page-placeholder">
      <div className="page-placeholder__accent" aria-hidden="true" />
      <div className="page-placeholder__eyebrow">{eyebrow}</div>
      {/* The placeholder is the whole page, so its title owns the h1. */}
      <h1 className="page-placeholder__title">{title}</h1>
      <div className="page-placeholder__body">{children}</div>
    </section>
  )
}