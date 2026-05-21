import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EmptyState } from '../EmptyState'

describe('EmptyState', () => {
  it('renders title and description with no action when action prop is omitted', () => {
    render(
      <EmptyState
        title="No data"
        description="Nothing to show yet."
      />,
    )

    expect(screen.getByText('No data')).toBeInTheDocument()
    expect(screen.getByText('Nothing to show yet.')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders the action node below the description when supplied', () => {
    render(
      <EmptyState
        title="No KB"
        description="Create one to continue."
        action={<button type="button">Create Knowledge Base</button>}
      />,
    )

    expect(
      screen.getByRole('button', { name: 'Create Knowledge Base' }),
    ).toBeInTheDocument()
  })

  it('falls back to the default title when title is omitted', () => {
    render(<EmptyState description="x" />)

    expect(screen.getByText('No data yet')).toBeInTheDocument()
  })
})
