import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getHousingInstallations, housingInstallationsQueryKey } from '../housing'
import { apiFetch } from '../client'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('housing API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('exposes stable query keys with optional period filters', () => {
    const filters = { periodStart: '2026-06-01', periodEnd: '2026-06-30' } as const

    expect(housingInstallationsQueryKey()).toEqual(['housing', 'installations', null])
    expect(housingInstallationsQueryKey(filters)).toEqual(['housing', 'installations', filters])
  })

  it('omits period params when filters are not provided', async () => {
    apiFetchMock.mockResolvedValue({})

    await getHousingInstallations()

    expect(apiFetchMock).toHaveBeenCalledWith('/housing/installations')
  })

  it('adds only provided optional period params', async () => {
    apiFetchMock.mockResolvedValue({})

    await getHousingInstallations({ periodEnd: '2026-06-30' })

    expect(apiFetchMock).toHaveBeenCalledWith('/housing/installations?period_end=2026-06-30')
  })
})
