import { describe, expect, it } from 'vitest'

import { flagLabelFor } from '../flagLabel'

describe('flagLabelFor', () => {
  it('joins tags uppercase with middle dots', () => {
    expect(flagLabelFor({ tags: ['upcoding', 'hcpcs-consolidation'], severity: 'high' })).toBe(
      'UPCODING · HCPCS-CONSOLIDATION',
    )
  })
  it('falls back to the severity word when no tags', () => {
    expect(flagLabelFor({ tags: [], severity: 'critical' })).toBe('CRITICAL')
  })
})
