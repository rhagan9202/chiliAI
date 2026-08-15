import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StatusChip } from '../StatusChip'
import { statusToken } from '../statusTokens'

describe('statusToken', () => {
  it('maps document extracted_empty to a distinct neutral state', () => {
    const token = statusToken('document', 'extracted_empty')
    expect(token.label).toBe('No entities')
    expect(token.tone).toBe('default')
  })
  it('maps document failed to danger', () => {
    expect(statusToken('document', 'failed').tone).toBe('danger')
  })
  it('reuses KB copy: active reads Empty', () => {
    expect(statusToken('knowledge-base', 'active').label).toBe('Empty')
  })
  it('sentence-cases unknown statuses', () => {
    expect(statusToken('workflow', 'some_new_state').label).toBe('Some new state')
  })
})

describe('StatusChip', () => {
  it('renders label and hint', () => {
    render(<StatusChip kind="document" status="extracted_empty" />)
    const chip = screen.getByText('No entities')
    expect(chip.closest('[title]')?.getAttribute('title')).toContain('contributed nothing')
  })
})
