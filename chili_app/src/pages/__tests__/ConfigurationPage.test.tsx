import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch, apiPost } from '../../api/client'
import type {
  ConfigSwapResponse,
  DomainConfig,
  DomainFeatures,
  PackListResponse,
} from '../../api/contracts'
import { SessionContext, type SessionState } from '../../contexts/sessionContextValue'
import { ConfigurationPage } from '../ConfigurationPage'

vi.mock('../../api/client', () => ({
  apiFetch: vi.fn(),
  apiPost: vi.fn(),
}))

// CodeMirror needs real DOM measurement APIs jsdom lacks; the page tests
// exercise the editor contract (value/onChange) through a plain textarea.
vi.mock('../../components/config/YamlEditor', () => ({
  YamlEditor: ({
    value,
    onChange,
    ariaLabel = 'Domain configuration editor',
  }: {
    value: string
    onChange: (next: string) => void
    ariaLabel?: string
  }) => (
    <textarea
      aria-label={ariaLabel}
      data-testid="yaml-editor"
      onChange={(event) => onChange(event.target.value)}
      value={value}
    />
  ),
}))

const apiFetchMock = vi.mocked(apiFetch)
const apiPostMock = vi.mocked(apiPost)

const capabilities = {
  timeseries: true,
  gnn: true,
  risk_scoring: true,
  rag_chat: true,
  explainability: true,
  peer_stats: true,
}

const domainConfig: DomainConfig = {
  domain: {
    name: 'medicare_fraud',
    display_name: 'Medicare Fraud Detection',
    description: 'Exemplar domain',
  },
  entities: [
    { name: 'provider', display_label: 'Provider', properties: {} },
    { name: 'claim', display_label: 'Claim', properties: {} },
  ],
  relationships: [
    { name: 'submitted_by', display_label: 'Submitted By', source: 'claim', target: 'provider' },
  ],
  capabilities,
  ingestion: {},
  alerts: { thresholds: {} },
}

const domainFeatures: DomainFeatures = {
  capabilities,
  default_entity_type: 'provider',
  default_role: 'analyst',
  enabled_pages: ['dashboard', 'configuration'],
  roles: {},
}

const packList: PackListResponse = {
  packs: [
    {
      name: 'medicare_fraud',
      file_name: 'medicare_fraud.yaml',
      path: '/config/defaults/medicare_fraud.yaml',
      domain_name: 'medicare_fraud',
      display_name: 'Medicare Fraud Detection',
      valid: true,
      error: null,
      active: true,
    },
    {
      name: 'food_supply_chain',
      file_name: 'food_supply_chain.yaml',
      path: '/config/defaults/food_supply_chain.yaml',
      domain_name: 'food_supply_chain',
      display_name: 'Food Supply Chain Integrity',
      valid: true,
      error: null,
      active: false,
    },
    {
      name: 'broken_pack',
      file_name: 'broken_pack.yaml',
      path: '/config/defaults/broken_pack.yaml',
      domain_name: null,
      display_name: null,
      valid: false,
      error: 'domain.name: Field required',
      active: false,
    },
  ],
  active: {
    config_path: '/config/defaults/medicare_fraud.yaml',
    pack_name: 'medicare_fraud',
    source: 'pointer',
    updated_at: '2026-07-01T00:00:00Z',
  },
  generation: 3,
}

const switchResponse: ConfigSwapResponse = {
  status: 'applied',
  reason: 'switch',
  pack_name: 'food_supply_chain',
  pack_path: '/config/defaults/food_supply_chain.yaml',
  previous_pack_name: 'medicare_fraud',
  generation: 4,
  rag_degraded_to_fallback: false,
  event_published: true,
}

function sessionState(roles: string[]): SessionState {
  return {
    status: 'authenticated',
    user: { user_id: 'user-1', roles, email: null },
    signOut: async () => {},
  }
}

function renderPage(roles: string[]) {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <SessionContext.Provider value={sessionState(roles)}>{children}</SessionContext.Provider>
      </QueryClientProvider>
    )
  }

  return { queryClient, ...render(<ConfigurationPage />, { wrapper: Wrapper }) }
}

beforeEach(() => {
  apiFetchMock.mockReset()
  apiPostMock.mockReset()
  apiFetchMock.mockImplementation((path: string) => {
    switch (path) {
      case '/config/domain':
        return Promise.resolve(domainConfig)
      case '/config/features':
        return Promise.resolve(domainFeatures)
      case '/config/domain/schema':
        return Promise.resolve({ properties: { domain: {} } })
      case '/config/packs':
        return Promise.resolve(packList)
      default:
        return Promise.reject(new Error(`Unexpected apiFetch call: ${path}`))
    }
  })
})

describe('ConfigurationPage admin gating', () => {
  it('renders only the read-only view for non-admin users', async () => {
    renderPage(['analyst'])

    expect(await screen.findByText('Medicare Fraud Detection')).toBeInTheDocument()
    expect(screen.queryByTestId('pack-switcher')).not.toBeInTheDocument()
    expect(screen.queryByTestId('active-pack-editor')).not.toBeInTheDocument()
    expect(apiFetchMock).not.toHaveBeenCalledWith('/config/packs')
  })

  it('renders the pack switcher and pack editor for admins', async () => {
    renderPage(['admin'])

    expect(await screen.findByTestId('pack-switcher')).toBeInTheDocument()
    expect(await screen.findByTestId('active-pack-editor')).toBeInTheDocument()
    expect(screen.getByTestId('config-generation')).toHaveTextContent('3')
  })
})

describe('pack switcher', () => {
  it('highlights the active pack and disables invalid packs with their error', async () => {
    renderPage(['admin'])

    const activeItem = await screen.findByTestId('pack-item-medicare_fraud')
    expect(activeItem).toHaveClass('pack-switcher__item--active')
    expect(within(activeItem).getByText('Active')).toBeInTheDocument()
    expect(within(activeItem).queryByRole('button', { name: 'Activate' })).not.toBeInTheDocument()

    const brokenItem = screen.getByTestId('pack-item-broken_pack')
    expect(within(brokenItem).getByText('Invalid')).toBeInTheDocument()
    expect(within(brokenItem).getByText('domain.name: Field required')).toBeInTheDocument()
    expect(within(brokenItem).getByRole('button', { name: 'Activate' })).toBeDisabled()
  })

  it('switches packs through a confirm step and reports the swap', async () => {
    apiPostMock.mockResolvedValue(switchResponse)
    const { queryClient } = renderPage(['admin'])
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const foodItem = await screen.findByTestId('pack-item-food_supply_chain')
    fireEvent.click(within(foodItem).getByRole('button', { name: 'Activate' }))

    // No request before the confirm step.
    expect(apiPostMock).not.toHaveBeenCalled()
    expect(
      within(foodItem).getByText(/Switch the whole workspace to “Food Supply Chain Integrity”\?/),
    ).toBeInTheDocument()

    fireEvent.click(within(foodItem).getByRole('button', { name: 'Confirm switch' }))

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith('/config/switch', { pack: 'food_supply_chain' })
    })
    const banner = await screen.findByTestId('swap-result')
    expect(banner).toHaveTextContent('Switched to food_supply_chain')
    expect(banner).toHaveTextContent('generation 4')

    const invalidatedKeys = invalidateSpy.mock.calls.map(([filters]) => filters?.queryKey)
    expect(invalidatedKeys).toEqual(
      expect.arrayContaining([
        ['domain-config'],
        ['domain-features'],
        ['domain-config-schema'],
        ['config-packs'],
      ]),
    )
  })

  it('cancelling the confirm step sends nothing', async () => {
    renderPage(['admin'])

    const foodItem = await screen.findByTestId('pack-item-food_supply_chain')
    fireEvent.click(within(foodItem).getByRole('button', { name: 'Activate' }))
    fireEvent.click(within(foodItem).getByRole('button', { name: 'Cancel' }))

    expect(apiPostMock).not.toHaveBeenCalled()
    expect(within(foodItem).getByRole('button', { name: 'Activate' })).toBeInTheDocument()
  })
})

describe('active pack editor', () => {
  async function findEditorTextarea() {
    const editor = await screen.findByTestId('active-pack-editor')
    return within(editor).getByTestId('yaml-editor')
  }

  it('seeds the buffer from the active domain config and gates Apply on validation', async () => {
    renderPage(['admin'])

    const textarea = (await findEditorTextarea()) as HTMLTextAreaElement
    await waitFor(() => {
      expect(textarea.value).toContain('medicare_fraud')
    })
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled()
  })

  it('renders a client-side parse error without calling the API', async () => {
    renderPage(['admin'])

    const textarea = await findEditorTextarea()
    fireEvent.change(textarea, { target: { value: 'domain: [unclosed' } })
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))

    const issues = await screen.findByTestId('validation-issues')
    expect(issues).toHaveTextContent(/YAML parse error/)
    expect(issues).toHaveTextContent('parse_error')
    expect(apiPostMock).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled()
  })

  it('renders field-level validation errors from POST /config/validate', async () => {
    apiPostMock.mockResolvedValue({
      valid: false,
      errors: [
        {
          loc: ['domain', 'display_name'],
          field: 'domain.display_name',
          message: 'Field required',
          error_type: 'missing',
        },
      ],
    })
    renderPage(['admin'])

    const textarea = await findEditorTextarea()
    fireEvent.change(textarea, { target: { value: 'domain:\n  name: broken\n' } })
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith('/config/validate', {
        content: { domain: { name: 'broken' } },
      })
    })
    const issues = await screen.findByTestId('validation-issues')
    expect(within(issues).getByText('domain.display_name')).toBeInTheDocument()
    expect(within(issues).getByText('Field required')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled()
  })

  it('enables Apply after a successful validate, re-gates on edit, and applies', async () => {
    apiPostMock.mockImplementation((path: string) => {
      if (path === '/config/validate') {
        return Promise.resolve({
          valid: true,
          pack_name: 'medicare_fraud',
          display_name: 'Medicare Fraud Detection',
          errors: [],
        })
      }
      if (path === '/config/apply') {
        return Promise.resolve({
          ...switchResponse,
          reason: 'apply',
          pack_name: 'medicare_fraud',
          previous_pack_name: 'medicare_fraud',
        })
      }
      return Promise.reject(new Error(`Unexpected apiPost call: ${path}`))
    })
    renderPage(['admin'])

    const textarea = await findEditorTextarea()
    fireEvent.change(textarea, { target: { value: 'domain:\n  name: medicare_fraud\n' } })
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))

    await screen.findByTestId('validate-success')
    const applyButton = screen.getByRole('button', { name: 'Apply' })
    expect(applyButton).toBeEnabled()

    // Any edit invalidates the previous validation and re-gates Apply.
    fireEvent.change(textarea, { target: { value: 'domain:\n  name: edited\n' } })
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))
    await screen.findByTestId('validate-success')
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith('/config/apply', {})
    })
    const banner = await screen.findByTestId('swap-result')
    expect(banner).toHaveTextContent('Applied medicare_fraud')
  })

  it('lets every summary count be opened to the items behind it', async () => {
    // The page reported "Entities loaded 8" with no way to see which eight —
    // a read-only stat dump about the thing that drives the product (UXA-404).
    renderPage(['analyst'])

    const entities = await screen.findByText('Entity types')
    const details = entities.closest('details')
    expect(details).not.toBeNull()
    fireEvent.click(entities)

    expect(within(details as HTMLElement).getByText('Provider')).toBeInTheDocument()
    expect(within(details as HTMLElement).getByText('Claim')).toBeInTheDocument()
  })

  it('shows the relationships and capabilities behind their counts', async () => {
    renderPage(['analyst'])

    const relationships = await screen.findByText('Relationship types')
    fireEvent.click(relationships)
    expect(
      within(relationships.closest('details') as HTMLElement).getByText('Submitted By'),
    ).toBeInTheDocument()

    const capabilitiesRow = await screen.findByText('Analysis enabled')
    fireEvent.click(capabilitiesRow)
    expect(
      within(capabilitiesRow.closest('details') as HTMLElement).getByText(/Graph clustering/),
    ).toBeInTheDocument()
  })
})
