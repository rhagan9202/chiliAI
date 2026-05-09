import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { KpiCard } from '../KpiCard'

describe('KpiCard', () => {
  it('renders the title and formatted numeric value when not loading', () => {
    render(<KpiCard title="Open Alerts" value={1234} />)
    expect(screen.getByText('Open Alerts')).toBeInTheDocument()
    expect(screen.getByText('1,234')).toBeInTheDocument()
  })

  it('renders a loading skeleton when loading is true', () => {
    render(<KpiCard title="Open Alerts" value={null} loading />)
    expect(screen.getByText('Open Alerts')).toBeInTheDocument()
    expect(
      screen.getByRole('status', { name: /Open Alerts loading/i }),
    ).toBeInTheDocument()
    expect(screen.queryByText('—')).not.toBeInTheDocument()
  })

  it('shows a placeholder when value is missing and not loading', () => {
    render(<KpiCard title="Active KBs" value={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders an error message when error is provided', () => {
    render(
      <KpiCard
        title="Total Entities"
        value={null}
        error="Failed to load metrics"
      />,
    )
    expect(screen.getByText('Failed to load metrics')).toBeInTheDocument()
  })
})
