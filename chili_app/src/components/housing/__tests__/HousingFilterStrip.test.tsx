import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { EMPTY_HOUSING_FILTERS } from '../housingFilters'
import { HousingFilterStrip } from '../HousingFilterStrip'

const noop = vi.fn()

function renderStrip(matchCount: number, totalCount: number, commands: string[] = []) {
  return render(
    <HousingFilterStrip
      commands={commands}
      filters={EMPTY_HOUSING_FILTERS}
      matchCount={matchCount}
      onClear={noop}
      onToggleBranch={noop}
      onToggleCommand={noop}
      onToggleStatus={noop}
      totalCount={totalCount}
    />,
  )
}

describe('HousingFilterStrip', () => {
  it('agrees in number when a single installation is in scope', () => {
    renderStrip(1, 1)

    expect(screen.getByText('Showing all 1 installation')).toBeInTheDocument()
  })

  it('pluralizes for many installations', () => {
    renderStrip(12, 12)

    expect(screen.getByText('Showing all 12 installations')).toBeInTheDocument()
  })
})
