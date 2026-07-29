import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useUiStore } from '../../../stores/uiStore'
import { LandingRedirect } from '../LandingRedirect'

const mocks = vi.hoisted(() => ({
  useDomainConfig: vi.fn(),
  useDomainFeatures: vi.fn(),
}))

vi.mock('../../../api/config', () => ({
  useDomainConfig: mocks.useDomainConfig,
  useDomainFeatures: mocks.useDomainFeatures,
}))

// A pack with no `dashboard` page at all — the shape that made the hardcoded
// "/" -> /dashboard redirect land every sign-in on "Page not available".
const housingConfig = {
  domain: {
    name: 'department_air_force_housing',
    display_name: 'Department of the Air Force Housing',
  },
  ui: {
    navigation: {
      pages: [
        { id: 'housing', label: 'Housing', route: '/housing', capability: null },
        {
          id: 'knowledge_bases',
          label: 'Knowledge Bases',
          route: '/knowledge-bases',
          capability: null,
        },
      ],
    },
  },
}

const housingFeatures = {
  default_role: 'executive',
  enabled_pages: ['housing', 'knowledge_bases'],
  roles: {
    executive: {
      landing_page: 'housing',
      pages: ['housing', 'knowledge_bases'],
      permissions: [],
    },
    analyst: {
      landing_page: 'knowledge_bases',
      pages: ['knowledge_bases'],
      permissions: [],
    },
  },
}

function renderLanding() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route element={<LandingRedirect />} path="/" />
        <Route element={<div>Housing body</div>} path="/housing" />
        <Route element={<div>Knowledge bases body</div>} path="/knowledge-bases" />
        <Route element={<div>Dashboard body</div>} path="/dashboard" />
      </Routes>
    </MemoryRouter>,
  )
}

describe('LandingRedirect', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useUiStore.setState({ selectedRole: null })
    mocks.useDomainConfig.mockReturnValue({ data: housingConfig, isLoading: false, isError: false })
    mocks.useDomainFeatures.mockReturnValue({
      data: housingFeatures,
      isLoading: false,
      isError: false,
    })
  })

  it('sends the user to the pack landing page rather than a hardcoded dashboard', () => {
    renderLanding()

    expect(screen.getByText('Housing body')).toBeInTheDocument()
    expect(screen.queryByText('Dashboard body')).not.toBeInTheDocument()
  })

  it('honours the active role landing page over the pack default', () => {
    useUiStore.setState({ selectedRole: 'analyst' })

    renderLanding()

    expect(screen.getByText('Knowledge bases body')).toBeInTheDocument()
  })

  it('waits for the pack instead of redirecting to a guess', () => {
    // Redirecting before the pack resolves is what produced the wrong landing
    // in the first place; nothing should be navigated to yet.
    mocks.useDomainConfig.mockReturnValue({ data: undefined, isLoading: true, isError: false })
    mocks.useDomainFeatures.mockReturnValue({ data: undefined, isLoading: true, isError: false })

    renderLanding()

    expect(screen.queryByText('Dashboard body')).not.toBeInTheDocument()
    expect(screen.queryByText('Housing body')).not.toBeInTheDocument()
  })
})
