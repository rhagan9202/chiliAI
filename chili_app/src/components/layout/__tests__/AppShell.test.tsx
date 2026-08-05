import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useUiStore } from '../../../stores/uiStore'
import { AppShell } from '../AppShell'

const mocks = vi.hoisted(() => ({
  useActiveKnowledgeBase: vi.fn(),
  useDomainConfig: vi.fn(),
  useDomainFeatures: vi.fn(),
  useKnowledgeBaseReadiness: vi.fn(),
}))

vi.mock('../../../api/config', () => ({
  useDomainConfig: mocks.useDomainConfig,
  useDomainFeatures: mocks.useDomainFeatures,
}))
vi.mock('../../../api/readiness', () => ({
  useKnowledgeBaseReadiness: mocks.useKnowledgeBaseReadiness,
}))
vi.mock('../../../api/realtime', () => ({ useRealtimeWorkspaceStream: () => undefined }))
vi.mock('../../../hooks/useActiveKnowledgeBase', () => ({
  useActiveKnowledgeBase: mocks.useActiveKnowledgeBase,
}))
vi.mock('../Sidebar', () => ({ Sidebar: () => <nav data-testid="sidebar" /> }))
vi.mock('../TopBar', () => ({
  TopBar: ({
    pageTitleOverride,
    workspaceControl,
  }: {
    pageTitleOverride?: string
    workspaceControl?: ReactNode
  }) => (
    <header data-testid="topbar">
      {pageTitleOverride ?? 'default title'}
      {workspaceControl}
    </header>
  ),
}))
vi.mock('../WorkspaceControl', () => ({
  WorkspaceControl: ({ activeKnowledgeBaseId }: { activeKnowledgeBaseId: string | null }) => (
    <div data-testid="workspace-control">{activeKnowledgeBaseId ?? 'no-kb'}</div>
  ),
}))
vi.mock('../AiAssistantPanel', () => ({ AiAssistantPanel: () => <aside data-testid="ai-panel" /> }))

const domainConfig = {
  domain: { name: 'medicare_fraud', display_name: 'Medicare Fraud Detection' },
  ui: {
    navigation: {
      pages: [
        { id: 'alerts', label: 'Alert Feed', route: '/alerts', capability: null },
        { id: 'configuration', label: 'Configuration', route: '/configuration', capability: null },
      ],
    },
  },
}

const domainFeatures = {
  default_role: 'analyst',
  enabled_pages: ['alerts', 'configuration', 'rag_chat'],
  roles: {
    analyst: { landing_page: 'alerts', pages: ['alerts', 'rag_chat'], permissions: [] },
    supervisor: {
      landing_page: 'alerts',
      pages: ['alerts', 'configuration'],
      permissions: [],
    },
  },
}

function renderShell(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route element={<AppShell />} path="/">
          <Route element={<div>Configuration page body</div>} path="configuration" />
          <Route element={<div>Alert feed body</div>} path="alerts" />
          <Route element={<div>Housing body</div>} path="housing" />
          <Route element={<div>RAG chat body</div>} path="rag-chat" />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('AppShell route access', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useUiStore.setState({ selectedRole: null })
    mocks.useDomainConfig.mockReturnValue({ data: domainConfig, isLoading: false, isError: false })
    mocks.useDomainFeatures.mockReturnValue({ data: domainFeatures, isLoading: false, isError: false })
    mocks.useActiveKnowledgeBase.mockReturnValue({
      activeKnowledgeBaseId: 'kb-ready',
      isError: false,
      isLoading: false,
      knowledgeBases: [],
      setActiveKnowledgeBase: vi.fn(),
    })
    mocks.useKnowledgeBaseReadiness.mockReturnValue({
      data: undefined,
      isError: false,
      isLoading: false,
    })
  })

  it('renders the page when the active role is allowed to open it', () => {
    useUiStore.setState({ selectedRole: 'supervisor' })

    renderShell('/configuration')

    expect(screen.getByText('Configuration page body')).toBeInTheDocument()
  })

  it('explains a denied route instead of silently redirecting away from it', () => {
    useUiStore.setState({ selectedRole: 'analyst' })

    renderShell('/configuration')

    // The analyst must be told what happened and which role governs it, rather
    // than being dropped on another page with no explanation.
    expect(screen.getByRole('heading', { name: /not available/i })).toBeInTheDocument()
    expect(
      screen.getByText(/the analyst role does not include this page/i),
    ).toBeInTheDocument()
    expect(screen.queryByText('Alert feed body')).not.toBeInTheDocument()
  })

  it('offers a way out of a denied route', () => {
    useUiStore.setState({ selectedRole: 'analyst' })

    renderShell('/configuration')

    expect(screen.getByRole('link', { name: /alert feed/i })).toHaveAttribute('href', '/alerts')
  })

  it('refuses a page this SPA implements that the active pack does not declare', () => {
    useUiStore.setState({ selectedRole: 'supervisor' })

    renderShell('/housing')

    expect(screen.getByRole('heading', { name: /not available/i })).toBeInTheDocument()
    expect(screen.queryByText('Housing body')).not.toBeInTheDocument()
  })

  it('does not announce another domain\'s page title on a refused route', () => {
    useUiStore.setState({ selectedRole: 'supervisor' })

    renderShell('/housing')

    // The body was already refused; the top bar must not still read
    // "Department of the Air Force Housing" under a Medicare pack.
    expect(screen.getByTestId('topbar')).toHaveTextContent('default title')
  })

  it('uses the role remembered from a previous session rather than the pack default', () => {
    // Persisted supervisor: a reload must not demote to `default_role` (analyst)
    // and bounce the user off the page they were on.
    window.localStorage.setItem('chiliai.selectedRole', 'supervisor')
    useUiStore.setState({ selectedRole: null })

    renderShell('/configuration')

    expect(screen.getByText('Configuration page body')).toBeInTheDocument()
  })

  it('refuses a restricted page to a role carried over from another pack', () => {
    // Switching packs leaves the previous pack's role in the store. Treating an
    // unrecognised role as "no role" collapsed gating to pack level, so this
    // page opened for a role that does not exist here while the real analyst
    // role is refused it.
    window.localStorage.setItem('chiliai.selectedRole', 'ghost')
    useUiStore.setState({ selectedRole: 'ghost' })

    renderShell('/configuration')

    expect(screen.getByRole('heading', { name: /not available/i })).toBeInTheDocument()
    expect(screen.queryByText('Configuration page body')).not.toBeInTheDocument()
  })

  it('reconciles a role carried over from another pack to the pack default', () => {
    // The stale value must actually be replaced, otherwise the role control
    // keeps displaying a role the pack does not have and the next reload is
    // refused all over again.
    window.localStorage.setItem('chiliai.selectedRole', 'ghost')
    useUiStore.setState({ selectedRole: 'ghost' })

    renderShell('/alerts')

    expect(useUiStore.getState().selectedRole).toBe('analyst')
    expect(window.localStorage.getItem('chiliai.selectedRole')).toBe('analyst')
  })
  it('does not hold the rail open on the page that is the assistant', () => {
    // RAG Chat has its own composer; showing the rail's too presented two
    // composers for the same job with nothing distinguishing them (UXA-407).
    useUiStore.setState({ aiPanelOpen: true })

    renderShell('/rag-chat')

    expect(screen.queryByTestId('ai-panel')).not.toBeInTheDocument()
  })

  it('keeps the rail on pages that can attach context to it', () => {
    useUiStore.setState({ aiPanelOpen: true })

    renderShell('/alerts')

    expect(screen.getByTestId('ai-panel')).toBeInTheDocument()
  })

  it('passes active KB workspace control into the top bar', () => {
    renderShell('/alerts')

    expect(screen.getByTestId('workspace-control')).toHaveTextContent('kb-ready')
    expect(mocks.useKnowledgeBaseReadiness).toHaveBeenCalledWith('kb-ready')
  })
})
