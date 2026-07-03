import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch, apiPost } from '../client'
import {
  applyPack,
  configPacksQueryKey,
  domainConfigInvalidationKeys,
  domainConfigQueryKey,
  domainConfigSchemaQueryKey,
  domainFeaturesQueryKey,
  getConfigPacks,
  switchPack,
  useApplyPack,
  useConfigPacks,
  useSwitchPack,
  useValidatePack,
  validatePack,
} from '../config'
import type {
  ConfigSwapResponse,
  PackListResponse,
  ValidatePackResponse,
} from '../contracts'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
  apiPost: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)
const apiPostMock = vi.mocked(apiPost)

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
  ],
  active: {
    config_path: '/config/defaults/medicare_fraud.yaml',
    pack_name: 'medicare_fraud',
    source: 'pointer',
    updated_at: '2026-07-01T00:00:00Z',
  },
  generation: 3,
}

const swapResponse: ConfigSwapResponse = {
  status: 'applied',
  reason: 'switch',
  pack_name: 'food_supply_chain',
  pack_path: '/config/defaults/food_supply_chain.yaml',
  previous_pack_name: 'medicare_fraud',
  generation: 4,
  rag_degraded_to_fallback: false,
  event_published: true,
}

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  })
}

function createQueryWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

function invalidatedQueryKeys(queryClient: QueryClient) {
  return vi
    .mocked(queryClient.invalidateQueries)
    .mock.calls.map(([filters]) => filters?.queryKey)
}

beforeEach(() => {
  apiFetchMock.mockReset()
  apiPostMock.mockReset()
})

describe('config pack API functions', () => {
  it('lists packs from GET /config/packs', async () => {
    apiFetchMock.mockResolvedValue(packList)

    await expect(getConfigPacks()).resolves.toBe(packList)

    expect(apiFetchMock).toHaveBeenCalledWith('/config/packs')
  })

  it('dry-run validates inline content via POST /config/validate', async () => {
    const response: ValidatePackResponse = {
      valid: true,
      pack_name: 'food_supply_chain',
      display_name: 'Food Supply Chain Integrity',
      errors: [],
    }
    apiPostMock.mockResolvedValue(response)

    const payload = { content: { domain: { name: 'food_supply_chain' } } }
    await expect(validatePack(payload)).resolves.toBe(response)

    expect(apiPostMock).toHaveBeenCalledWith('/config/validate', payload)
  })

  it('applies the active pack via POST /config/apply', async () => {
    apiPostMock.mockResolvedValue({ ...swapResponse, reason: 'apply' })

    await applyPack({})

    expect(apiPostMock).toHaveBeenCalledWith('/config/apply', {})
  })

  it('switches packs via POST /config/switch', async () => {
    apiPostMock.mockResolvedValue(swapResponse)

    await switchPack({ pack: 'food_supply_chain' })

    expect(apiPostMock).toHaveBeenCalledWith('/config/switch', { pack: 'food_supply_chain' })
  })
})

describe('config pack hooks', () => {
  it('useConfigPacks fetches only when enabled', async () => {
    apiFetchMock.mockResolvedValue(packList)
    const queryClient = createTestQueryClient()
    const wrapper = createQueryWrapper(queryClient)

    const disabled = renderHook(() => useConfigPacks({ enabled: false }), { wrapper })
    expect(apiFetchMock).not.toHaveBeenCalled()
    disabled.unmount()

    const { result } = renderHook(() => useConfigPacks(), { wrapper })
    await waitFor(() => {
      expect(result.current.data).toEqual(packList)
    })
    expect(apiFetchMock).toHaveBeenCalledWith('/config/packs')
  })

  it('useValidatePack does not invalidate any config queries', async () => {
    apiPostMock.mockResolvedValue({ valid: true, errors: [] })
    const queryClient = createTestQueryClient()
    vi.spyOn(queryClient, 'invalidateQueries')
    const wrapper = createQueryWrapper(queryClient)

    const { result } = renderHook(() => useValidatePack(), { wrapper })
    result.current.mutate({ content: {} })
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(queryClient.invalidateQueries).not.toHaveBeenCalled()
  })

  const expectedSwapInvalidationKeys = [
    domainConfigQueryKey,
    domainFeaturesQueryKey,
    domainConfigSchemaQueryKey,
    configPacksQueryKey,
  ]

  it('useSwitchPack invalidates the domain-config query keys on success (hot swap)', async () => {
    apiPostMock.mockResolvedValue(swapResponse)
    const queryClient = createTestQueryClient()
    vi.spyOn(queryClient, 'invalidateQueries')
    const wrapper = createQueryWrapper(queryClient)

    const { result } = renderHook(() => useSwitchPack(), { wrapper })
    result.current.mutate({ pack: 'food_supply_chain' })
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(invalidatedQueryKeys(queryClient)).toEqual(
      expect.arrayContaining(expectedSwapInvalidationKeys),
    )
  })

  it('useApplyPack invalidates the domain-config query keys on success (hot swap)', async () => {
    apiPostMock.mockResolvedValue({ ...swapResponse, reason: 'apply' })
    const queryClient = createTestQueryClient()
    vi.spyOn(queryClient, 'invalidateQueries')
    const wrapper = createQueryWrapper(queryClient)

    const { result } = renderHook(() => useApplyPack(), { wrapper })
    result.current.mutate({})
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(invalidatedQueryKeys(queryClient)).toEqual(
      expect.arrayContaining(expectedSwapInvalidationKeys),
    )
  })

  it('exports the providers.tsx domain-config key set as the invalidation contract', () => {
    expect(domainConfigInvalidationKeys).toEqual([
      domainConfigQueryKey,
      domainFeaturesQueryKey,
      domainConfigSchemaQueryKey,
    ])
  })
})
