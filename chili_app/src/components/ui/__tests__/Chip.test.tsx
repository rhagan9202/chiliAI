import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Chip } from '../Chip'

describe('Chip', () => {
  it('renders its label', () => {
    render(<Chip label="Ready" />)

    expect(screen.getByText('Ready')).toBeInTheDocument()
  })

  it('carries an optional explanation for a label that needs one', () => {
    // Status chips are terse by design; the hint is where the meaning lives.
    render(<Chip label="Empty" title="Created, but nothing has been ingested yet." />)

    expect(screen.getByText('Empty')).toHaveAttribute(
      'title',
      'Created, but nothing has been ingested yet.',
    )
  })

  it('omits the title attribute when no explanation is given', () => {
    render(<Chip label="Ready" />)

    expect(screen.getByText('Ready')).not.toHaveAttribute('title')
  })
})
