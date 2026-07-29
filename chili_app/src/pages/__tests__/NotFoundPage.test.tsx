import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NotFoundPage } from '../NotFoundPage'

const mocks = vi.hoisted(() => ({
  useDomainConfig: vi.fn(),
  useDomainFeatures: vi.fn(),
}))

vi.mock('../../api/config', () => ({
  useDomainConfig: mocks.useDomainConfig,
  useDomainFeatures: mocks.useDomainFeatures,
}))

const features = {
  default_role: 'analyst',
  enabled_pages: ['dashboard', 'scorecards'],
  roles: {
    analyst: { landing_page: 'dashboard', pages: ['dashboard', 'scorecards'], permissions: [] },
  },
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <NotFoundPage />
    </MemoryRouter>,
  )
}

describe('NotFoundPage', () => {
  beforeEach(() => {
    mocks.useDomainConfig.mockReturnValue({
      data: {
        ui: {
          navigation: {
            pages: [
              { id: 'dashboard', label: 'Dashboard', route: '/dashboard' },
              { id: 'scorecards', label: 'Scorecards', route: '/scorecards' },
            ],
          },
        },
      },
    })
    mocks.useDomainFeatures.mockReturnValue({ data: features })
  })

  it('tells a user with a mistyped address that the page does not exist', () => {
    renderAt('/alertz')

    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByText(/\/alertz/)).toBeInTheDocument()
  })

  it('offers a way back to the workspace', () => {
    renderAt('/alertz')

    expect(screen.getByRole('link', { name: /dashboard/i })).toHaveAttribute('href', '/dashboard')
  })

  it('explains that a configured but unbuilt page is coming, not missing', () => {
    renderAt('/scorecards')

    expect(screen.getByRole('heading', { level: 1, name: 'Not available yet' })).toBeInTheDocument()
  })

  it('falls back to not found while the workspace configuration is still loading', () => {
    mocks.useDomainConfig.mockReturnValue({ data: undefined })

    renderAt('/scorecards')

    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument()
  })

  it('points at the landing page of a pack that has no dashboard', () => {
    // The housing pack enables no dashboard, so a hardcoded "/dashboard" escape
    // sent anyone who mistyped an address straight to "Page not available" —
    // a wrong turn leading to a refusal instead of back to the workspace.
    mocks.useDomainConfig.mockReturnValue({
      data: {
        ui: {
          navigation: {
            pages: [{ id: 'housing', label: 'Housing', route: '/housing' }],
          },
        },
      },
    })
    mocks.useDomainFeatures.mockReturnValue({
      data: {
        default_role: 'executive',
        enabled_pages: ['housing'],
        roles: {
          executive: { landing_page: 'housing', pages: ['housing'], permissions: [] },
        },
      },
    })

    renderAt('/alertz')

    expect(screen.getByRole('link', { name: /housing/i })).toHaveAttribute('href', '/housing')
    expect(screen.queryByRole('link', { name: /dashboard/i })).not.toBeInTheDocument()
  })
})
