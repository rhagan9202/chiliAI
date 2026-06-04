import { describe, expect, it, vi } from 'vitest'

import * as client from '../client'
import { getPolicyItems, getPolicyItem, triagePolicyItem } from '../policy'

describe('policy api client', () => {
  it('threads knowledge_base_id and status into requests', async () => {
    const apiFetch = vi.spyOn(client, 'apiFetch').mockResolvedValue({ items: [], total: 0 })
    await getPolicyItems('kb-1', 'open')
    expect(apiFetch).toHaveBeenCalledWith('/policy/items?knowledge_base_id=kb-1&status=open')

    apiFetch.mockResolvedValue({ item: {}, matched_fields: {}, citations: [] })
    await getPolicyItem('kb-1', 'item-9')
    expect(apiFetch).toHaveBeenCalledWith('/policy/items/item-9?knowledge_base_id=kb-1')
  })

  it('posts triage actions', async () => {
    const apiPost = vi.spyOn(client, 'apiPost').mockResolvedValue({ item: {}, matched_fields: {}, citations: [] })
    await triagePolicyItem('kb-1', 'item-9', { action: 'escalate', note: 'urgent' })
    expect(apiPost).toHaveBeenCalledWith(
      '/policy/items/item-9/triage?knowledge_base_id=kb-1',
      { action: 'escalate', note: 'urgent' },
    )
  })
})
