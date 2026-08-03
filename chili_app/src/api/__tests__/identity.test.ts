import { apiFetch } from '../client'
import {
  getCanonicalIdentityDetail,
  identityLinksQueryKey,
} from '../identity'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)

describe('identity api helpers', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('serializes canonical identity detail scope and entity id', async () => {
    apiFetchMock.mockResolvedValue({ links: [] })

    await getCanonicalIdentityDetail('kb 1', 'provider:204')

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/identity/canonical/provider%3A204?knowledge_base_id=kb+1',
    )
  })

  it('keys identity links by knowledge base and canonical entity', () => {
    expect(identityLinksQueryKey('kb-1', 'provider-1')).not.toEqual(
      identityLinksQueryKey('kb-2', 'provider-1'),
    )
    expect(identityLinksQueryKey('kb-1', 'provider-1')).not.toEqual(
      identityLinksQueryKey('kb-1', 'provider-2'),
    )
  })
})
