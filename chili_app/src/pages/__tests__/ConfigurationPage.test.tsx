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
  // The active side of the transport comparison (UXA-404).
  events: {
    backend: 'redis',
    uri: 'redis://redis:6379',
    stream_prefix: 'chili',
    consumer_group: 'chili-workers',
    stream_maxlen: null,
    reclaim_min_idle_ms: null,
  },
}

const REDIS_TRANSPORT = {
  backend: 'redis',
  uri: 'redis://redis:6379',
  stream_prefix: 'chili',
  consumer_group: 'chili-workers',
}

/** A schema with a $ref, a list-of-$ref, an enum and a cycle. */
const domainSchema = {
  properties: {
    domain: { $ref: '#/$defs/DomainInfo' },
    entities: { items: { $ref: '#/$defs/EntityDefinition' }, type: 'array' },
    events: { anyOf: [{ $ref: '#/$defs/EventBusConfig' }, { type: 'null' }], default: null },
  },
  required: ['domain', 'entities'],
  $defs: {
    DomainInfo: {
      type: 'object',
      required: ['name'],
      properties: {
        name: { type: 'string', description: 'Machine name for the domain.' },
      },
    },
    EntityDefinition: {
      type: 'object',
      properties: { children: { items: { $ref: '#/$defs/EntityDefinition' }, type: 'array' } },
    },
    EventBusConfig: {
      type: 'object',
      properties: {
        backend: { enum: ['redis', 'in_memory'], type: 'string', default: 'in_memory' },
      },
    },
  },
}

const domainFeatures: DomainFeatures = {
  capabilities,
  default_entity_type: 'provider',
  default_role: 'analyst',
  enabled_pages: ['dashboard', 'configuration'],
  roles: {},
}

const knowledgeBases = {
  items: [
    {
      id: 'kb-1',
      name: 'CMS Fraud KB',
      description: 'Medicare fraud workspace',
      domain: 'medicare_fraud',
      document_count: 3,
      status: 'ready',
      created_at: '2026-08-05T12:00:00Z',
      updated_at: '2026-08-05T12:00:00Z',
    },
  ],
  total: 1,
}

const capabilityRegistry = {
  items: [
    {
      capability_id: 'rag.query',
      version: 'v1',
      module: 'rag',
      label: 'Scoped RAG query',
      description: 'Query knowledge base context with explicit scope and citations.',
      input_schema: {
        type: 'object',
        properties: {
          query: { type: 'string' },
          scope: { type: 'object' },
        },
      },
      output_schema: {
        type: 'object',
        properties: {
          answer: { type: 'string' },
          citation_refs: { type: 'array' },
        },
      },
      side_effect_class: 'read',
      permission: {
        required_roles: ['viewer'],
        requires_audit: false,
        required_scopes: [],
      },
      domain_compatibility: {
        supported_domains: ['medicare_fraud'],
        unsupported_domains: [],
        environment_tags: ['dev', 'test', 'production'],
      },
      health: {
        status: 'healthy',
        last_checked_at: null,
        details: null,
      },
      examples: [
        {
          name: 'Alert context query',
          input: { query: 'Why is this provider unusual?' },
          output: { answer: 'Peer billing is elevated.' },
        },
      ],
    },
  ],
  total: 1,
  limit: 100,
  offset: 0,
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
      transport: REDIS_TRANSPORT,
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
      // Same Redis, different consumer group: queued work is abandoned.
      transport: { ...REDIS_TRANSPORT, consumer_group: 'food-workers' },
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
      // An unloadable pack resolves to nothing; unknown is not a change.
      transport: null,
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
        return Promise.resolve(domainSchema)
      case '/config/packs':
        return Promise.resolve(packList)
      case '/knowledgebases':
        return Promise.resolve(knowledgeBases)
      case '/knowledgebases/kb-1/capabilities?limit=100&offset=0':
        return Promise.resolve(capabilityRegistry)
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

  it('warns what a transport change costs, above the confirm button (UXA-404)', async () => {
    renderPage(['admin'])

    const item = await screen.findByTestId('pack-item-food_supply_chain')
    fireEvent.click(within(item).getByRole('button', { name: 'Activate' }))

    const warning = within(item).getByTestId('transport-warning')
    expect(warning).toHaveAttribute('data-severity', 'changed')
    expect(warning).toHaveTextContent('consumer_group')
    expect(warning).toHaveTextContent('chili-workers → food-workers')
    expect(warning).toHaveTextContent(/abandoned/)
    // Read before the irreversible click, not explained after it.
    expect(
      warning.compareDocumentPosition(within(item).getByRole('button', { name: 'Confirm switch' })),
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('says nothing when the transport is unchanged', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/config/packs') {
        return Promise.resolve({
          ...packList,
          packs: packList.packs.map((pack) =>
            pack.name === 'food_supply_chain' ? { ...pack, transport: REDIS_TRANSPORT } : pack,
          ),
        })
      }
      if (path === '/config/domain') return Promise.resolve(domainConfig)
      if (path === '/config/features') return Promise.resolve(domainFeatures)
      if (path === '/config/domain/schema') return Promise.resolve(domainSchema)
      return Promise.reject(new Error(`Unexpected apiFetch call: ${path}`))
    })
    renderPage(['admin'])

    const item = await screen.findByTestId('pack-item-food_supply_chain')
    fireEvent.click(within(item).getByRole('button', { name: 'Activate' }))

    expect(within(item).queryByTestId('transport-warning')).not.toBeInTheDocument()
  })

  it('escalates the wording when a swap would decouple the API from the worker', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/config/packs') {
        return Promise.resolve({
          ...packList,
          packs: packList.packs.map((pack) =>
            pack.name === 'food_supply_chain'
              ? { ...pack, transport: { ...REDIS_TRANSPORT, backend: 'in-memory', uri: null } }
              : pack,
          ),
        })
      }
      if (path === '/config/domain') return Promise.resolve(domainConfig)
      if (path === '/config/features') return Promise.resolve(domainFeatures)
      if (path === '/config/domain/schema') return Promise.resolve(domainSchema)
      return Promise.reject(new Error(`Unexpected apiFetch call: ${path}`))
    })
    renderPage(['admin'])

    const item = await screen.findByTestId('pack-item-food_supply_chain')
    fireEvent.click(within(item).getByRole('button', { name: 'Activate' }))

    const warning = within(item).getByTestId('transport-warning')
    expect(warning).toHaveAttribute('data-severity', 'decoupled')
    expect(warning).toHaveTextContent(/separate processes/)
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

  it('makes an issue whose field is in the buffer a control that reveals it (UXA-404)', async () => {
    // The dotted path said what was wrong; it did not say where to look.
    apiPostMock.mockResolvedValue({
      valid: false,
      errors: [
        {
          loc: ['domain', 'name'],
          field: 'domain.name',
          message: 'String should match pattern',
          error_type: 'string_pattern_mismatch',
        },
      ],
    })
    renderPage(['admin'])

    const textarea = await findEditorTextarea()
    fireEvent.change(textarea, { target: { value: 'domain:\n  name: Not A Slug\n' } })
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))

    const issues = await screen.findByTestId('validation-issues')
    expect(within(issues).getByRole('button', { name: 'domain.name' })).toBeInTheDocument()
  })

  it('leaves an unlocatable issue as plain text rather than a dead control', async () => {
    // A file-level parse error carries no path, and the buffer may have moved
    // on since it was validated.
    apiPostMock.mockResolvedValue({
      valid: false,
      errors: [
        {
          loc: [],
          field: '',
          message: 'Pack must be a mapping.',
          error_type: 'parse_error',
        },
        {
          loc: ['domain', 'gone'],
          field: 'domain.gone',
          message: 'Field required',
          error_type: 'missing',
        },
      ],
    })
    renderPage(['admin'])

    const textarea = await findEditorTextarea()
    fireEvent.change(textarea, { target: { value: 'domain:\n  name: ok\n' } })
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))

    const issues = await screen.findByTestId('validation-issues')
    expect(within(issues).queryByRole('button')).not.toBeInTheDocument()
    expect(within(issues).getByText('domain.gone')).toBeInTheDocument()
    expect(within(issues).getByText('Pack must be a mapping.')).toBeInTheDocument()
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

  it('browses the schema down to fields, types and defaults (UXA-404)', async () => {
    // The page listed 27 property names, which answers nothing an operator
    // writing a pack asks.
    renderPage(['analyst'])

    const browser = await screen.findByTestId('schema-browser')
    fireEvent.click(within(browser).getByText('Schema sections'))

    // A section resolves through its $ref to the fields behind it.
    fireEvent.click(within(browser).getByText('domain'))
    expect(within(browser).getByText('Machine name for the domain.')).toBeInTheDocument()
    expect(within(browser).getByText('required')).toBeInTheDocument()

    // An enum renders as the values it accepts, with its default.
    fireEvent.click(within(browser).getByText('events'))
    expect(within(browser).getByText('one of: redis, in_memory')).toBeInTheDocument()
    expect(within(browser).getByText(/default in_memory/)).toBeInTheDocument()
  })

  it('stops a self-referential definition instead of expanding forever', async () => {
    renderPage(['analyst'])

    const browser = await screen.findByTestId('schema-browser')
    fireEvent.click(within(browser).getByText('Schema sections'))
    fireEvent.click(within(browser).getByText('entities'))

    // The entities section already resolved through EntityDefinition, so its
    // self-referential `children` field points back instead of expanding —
    // one "array of EntityDefinition" on screen, not a chain of them.
    expect(within(browser).getByText('array of EntityDefinition')).toBeInTheDocument()
    expect(within(browser).getByText(/Repeats/)).toBeInTheDocument()
  })

  it('says so when the schema is unavailable', async () => {
    apiFetchMock.mockImplementation((path: string) => {
      if (path === '/config/domain/schema') return Promise.resolve({})
      if (path === '/config/domain') return Promise.resolve(domainConfig)
      if (path === '/config/features') return Promise.resolve(domainFeatures)
      return Promise.reject(new Error(`Unexpected apiFetch call: ${path}`))
    })
    renderPage(['analyst'])

    const browser = await screen.findByTestId('schema-browser')
    fireEvent.click(within(browser).getByText('Schema sections'))

    expect(within(browser).getByText('The pack schema is unavailable.')).toBeInTheDocument()
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

  it('shows the active KB capability registry with permissions, schema, domain, health and examples', async () => {
    renderPage(['analyst'])

    const browser = await screen.findByTestId('capability-registry-browser')

    expect(within(browser).getByText('CMS Fraud KB')).toBeInTheDocument()
    expect(within(browser).getByText('Scoped RAG query')).toBeInTheDocument()
    expect(within(browser).getByText('viewer')).toBeInTheDocument()
    expect(within(browser).getByText('No audit')).toBeInTheDocument()
    expect(within(browser).getByText('medicare_fraud')).toBeInTheDocument()
    expect(within(browser).getByText('healthy')).toBeInTheDocument()
    expect(within(browser).getByText('query, scope')).toBeInTheDocument()
    expect(within(browser).getByText('answer, citation_refs')).toBeInTheDocument()
    expect(within(browser).getByText('Alert context query')).toBeInTheDocument()
  })
})
