import { apiFetch } from '../client'
import {
  entityFeatureValuesQueryKey,
  featureCatalogQueryKey,
  getEntityFeatureValues,
  getFeatureCatalog,
} from '../features'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('feature api helpers', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('fetches the KB-scoped feature catalog', async () => {
    apiFetchMock.mockResolvedValue({ catalog_version: 'cms-fraud-features-v1' })

    await getFeatureCatalog('kb-1')

    expect(apiFetchMock).toHaveBeenCalledWith('/knowledgebases/kb-1/features/catalog')
  })

  it('encodes entity feature value path segments', async () => {
    apiFetchMock.mockResolvedValue({ items: [] })

    await getEntityFeatureValues('kb/with slash', 'provider', 'npi 123')

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/knowledgebases/kb%2Fwith%20slash/entities/provider/npi%20123/features',
    )
  })

  it('keys catalog and entity values by scope', () => {
    expect(featureCatalogQueryKey('kb-1')).not.toEqual(featureCatalogQueryKey('kb-2'))
    expect(entityFeatureValuesQueryKey('kb-1', 'provider', 'npi-1')).not.toEqual(
      entityFeatureValuesQueryKey('kb-1', 'provider', 'npi-2'),
    )
  })
})
