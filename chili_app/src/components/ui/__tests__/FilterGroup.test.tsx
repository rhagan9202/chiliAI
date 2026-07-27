import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { FilterGroup } from '../FilterGroup'

const OPTIONS = [
  { id: 'critical', label: 'Critical', count: 2 },
  { id: 'high', label: 'High', count: 0 },
]

describe('FilterGroup', () => {
  it('labels the dimension it filters on', () => {
    render(<FilterGroup label="Severity" onToggle={vi.fn()} options={OPTIONS} selected={[]} />)

    expect(screen.getByRole('group', { name: 'Severity' })).toBeInTheDocument()
  })

  it('shows each option with the count it would return', () => {
    render(<FilterGroup label="Severity" onToggle={vi.fn()} options={OPTIONS} selected={[]} />)

    expect(screen.getByRole('button', { name: 'Critical, 2 matching' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'High, 0 matching' })).toBeInTheDocument()
  })

  it('announces which options are selected', () => {
    render(
      <FilterGroup label="Severity" onToggle={vi.fn()} options={OPTIONS} selected={['critical']} />,
    )

    expect(screen.getByRole('button', { name: 'Critical, 2 matching' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByRole('button', { name: 'High, 0 matching' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('reports the option toggled rather than a whole new selection', () => {
    const onToggle = vi.fn()
    render(<FilterGroup label="Severity" onToggle={onToggle} options={OPTIONS} selected={[]} />)

    return userEvent.click(screen.getByRole('button', { name: 'Critical, 2 matching' })).then(() => {
      expect(onToggle).toHaveBeenCalledWith('critical')
    })
  })

  it('renders nothing when the dimension has no options', () => {
    const { container } = render(
      <FilterGroup label="Severity" onToggle={vi.fn()} options={[]} selected={[]} />,
    )

    expect(container).toBeEmptyDOMElement()
  })
})
