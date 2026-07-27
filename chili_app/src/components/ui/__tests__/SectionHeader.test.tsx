import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SectionHeader } from '../SectionHeader'

describe('SectionHeader', () => {
  it('renders the page title as the h1', () => {
    // The page — not the constant domain chrome in the top bar — owns the h1.
    // Previously every route's only h1 was the domain name, so heading
    // navigation reported all 11 pages under the same name (UXA-205).
    render(<SectionHeader eyebrow="Triage queue" title="Alert Feed" />)

    expect(
      screen.getByRole('heading', { level: 1, name: 'Alert Feed' }),
    ).toBeInTheDocument()
  })

  it('renders the eyebrow and subtitle as supporting text, not headings', () => {
    render(
      <SectionHeader
        eyebrow="Triage queue"
        subtitle="Review flagged entities."
        title="Alert Feed"
      />,
    )

    expect(screen.getByText('Triage queue')).toBeInTheDocument()
    expect(screen.getByText('Review flagged entities.')).toBeInTheDocument()
    expect(screen.getAllByRole('heading')).toHaveLength(1)
  })
})
