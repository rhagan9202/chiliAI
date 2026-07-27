import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { DomainConfig, DomainFeatures } from '../../../api/contracts'
import { TopBar } from '../TopBar'

const foodSupplyConfig = {
  domain: { display_name: 'Food Supply Chain Integrity' },
} as DomainConfig

const domainFeatures = {
  roles: {
    executive: {
      default: true,
      pages: ['/housing'],
    },
  },
} as unknown as DomainFeatures

describe('TopBar', () => {
  it('uses an explicit page title override ahead of the active domain name', () => {
    render(
      <TopBar
        domainConfig={foodSupplyConfig}
        domainFeatures={domainFeatures}
        loading={false}
        pageTitleOverride="Department of the Air Force Housing"
        unavailable={false}
      />,
    )

    // The domain title is constant chrome, deliberately not a heading — the
    // page owns the h1 via SectionHeader (UXA-205).
    expect(screen.getByText('Department of the Air Force Housing')).toBeInTheDocument()
    expect(screen.queryByText('Food Supply Chain Integrity')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
  })
})
