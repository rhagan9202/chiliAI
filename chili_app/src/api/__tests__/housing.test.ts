import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  getHousingInstallations,
  getHousingOverview,
  housingInstallationsQueryKey,
  housingOverviewQueryKey,
} from '../housing'
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

    expect(housingOverviewQueryKey()).toEqual(['housing', 'overview', null])
    expect(housingOverviewQueryKey(filters)).toEqual(['housing', 'overview', filters])
    expect(housingInstallationsQueryKey(filters)).toEqual(['housing', 'installations', filters])
  })

  it('omits period params when filters are not provided', async () => {
    apiFetchMock.mockResolvedValue({})

    await getHousingOverview()
    await getHousingInstallations()

    expect(apiFetchMock).toHaveBeenNthCalledWith(1, '/housing/overview')
    expect(apiFetchMock).toHaveBeenNthCalledWith(2, '/housing/installations')
  })

  it('adds only provided optional period params', async () => {
    apiFetchMock.mockResolvedValue({})

    await getHousingOverview({ periodStart: '2026-06-01' })
    await getHousingInstallations({ periodEnd: '2026-06-30' })

    expect(apiFetchMock).toHaveBeenNthCalledWith(
      1,
      '/housing/overview?period_start=2026-06-01',
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      2,
      '/housing/installations?period_end=2026-06-30',
    )
  })
})
