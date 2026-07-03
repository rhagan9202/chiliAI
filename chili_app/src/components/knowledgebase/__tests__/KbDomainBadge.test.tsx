import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { isDomainMismatch } from '../domainMismatch'
import { KbDomainBadge } from '../KbDomainBadge'

describe('isDomainMismatch', () => {
  it('is true when the KB domain differs from the active domain', () => {
    expect(isDomainMismatch('medicare_fraud', 'food_supply_chain')).toBe(true)
  })

  it('is false when the KB domain matches the active domain', () => {
    expect(isDomainMismatch('medicare_fraud', 'medicare_fraud')).toBe(false)
  })

  it('is false when either domain is unknown', () => {
    expect(isDomainMismatch(null, 'medicare_fraud')).toBe(false)
    expect(isDomainMismatch(undefined, 'medicare_fraud')).toBe(false)
    expect(isDomainMismatch('medicare_fraud', null)).toBe(false)
    expect(isDomainMismatch('medicare_fraud', undefined)).toBe(false)
    expect(isDomainMismatch(null, null)).toBe(false)
  })
})

describe('KbDomainBadge', () => {
  it('shows a warning badge when the KB domain differs from the active domain', () => {
    render(<KbDomainBadge kbDomain="medicare_fraud" activeDomainName="food_supply_chain" />)

    const badge = screen.getByTestId('kb-domain-mismatch')
    expect(badge).toBeInTheDocument()
    expect(screen.getByText('Created under medicare_fraud')).toBeInTheDocument()
    // Warn only — the badge explains that nothing is blocked.
    expect(badge).toHaveAttribute('title', expect.stringContaining('No action is blocked'))
    expect(screen.queryByTestId('kb-domain-unknown')).not.toBeInTheDocument()
  })

  it('renders nothing when the KB domain matches the active domain', () => {
    const { container } = render(
      <KbDomainBadge kbDomain="medicare_fraud" activeDomainName="medicare_fraud" />,
    )

    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByTestId('kb-domain-mismatch')).not.toBeInTheDocument()
    expect(screen.queryByTestId('kb-domain-unknown')).not.toBeInTheDocument()
  })

  it('renders a tolerated unknown state without warning styling for a null KB domain', () => {
    render(<KbDomainBadge kbDomain={null} activeDomainName="medicare_fraud" />)

    expect(screen.getByTestId('kb-domain-unknown')).toBeInTheDocument()
    expect(screen.getByText('domain unknown')).toBeInTheDocument()
    expect(screen.queryByTestId('kb-domain-mismatch')).not.toBeInTheDocument()
  })

  it('treats an undefined KB domain the same as null', () => {
    render(<KbDomainBadge kbDomain={undefined} activeDomainName="medicare_fraud" />)

    expect(screen.getByTestId('kb-domain-unknown')).toBeInTheDocument()
    expect(screen.queryByTestId('kb-domain-mismatch')).not.toBeInTheDocument()
  })
})
