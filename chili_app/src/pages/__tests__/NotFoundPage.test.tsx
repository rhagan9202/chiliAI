import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NotFoundPage } from '../NotFoundPage'

const mocks = vi.hoisted(() => ({
  useDomainConfig: vi.fn(),
}))

vi.mock('../../api/config', () => ({
  useDomainConfig: mocks.useDomainConfig,
}))

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
})
