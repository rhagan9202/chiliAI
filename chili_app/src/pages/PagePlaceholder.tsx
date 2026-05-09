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
      <h2 className="page-placeholder__title">{title}</h2>
      <div className="page-placeholder__body">{children}</div>
    </section>
  )
}