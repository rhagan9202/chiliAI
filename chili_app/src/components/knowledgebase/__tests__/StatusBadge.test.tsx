import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StatusBadge } from '../StatusBadge'

describe('StatusBadge', () => {
  it('names the empty state instead of echoing the API word "active"', () => {
    render(<StatusBadge status="active" />)

    expect(screen.getByTestId('kb-status-badge')).toHaveTextContent('Empty')
  })

  it('explains the state on hover', () => {
    render(<StatusBadge status="active" />)

    expect(screen.getByTestId('kb-status-badge')).toHaveAttribute(
      'title',
      'Created, but nothing has been ingested yet.',
    )
  })

  it('keeps the raw status as data for styling and end-to-end selectors', () => {
    render(<StatusBadge status="ready" />)

    const badge = screen.getByTestId('kb-status-badge')
    expect(badge).toHaveAttribute('data-status', 'ready')
    expect(badge).toHaveTextContent('Ready')
  })
})
