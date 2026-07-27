import { describe, expect, it } from 'vitest'

import { countLabel } from '../countLabel'

describe('countLabel', () => {
  it('uses the singular noun for exactly one', () => {
    expect(countLabel(1, 'alert')).toBe('1 alert')
  })

  it('uses the plural noun for zero', () => {
    expect(countLabel(0, 'alert')).toBe('0 alerts')
  })

  it('uses the plural noun for many', () => {
    expect(countLabel(2, 'alert')).toBe('2 alerts')
  })

  it('accepts an irregular plural', () => {
    expect(countLabel(1, 'entity', 'entities')).toBe('1 entity')
    expect(countLabel(3, 'entity', 'entities')).toBe('3 entities')
  })

  it('groups thousands so large queues stay readable', () => {
    expect(countLabel(12345, 'alert')).toBe('12,345 alerts')
  })
})
