import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SourceTypeStep } from '../SourceTypeStep'

describe('SourceTypeStep', () => {
  it('calls onChange when a source choice is clicked', () => {
    const onChange = vi.fn()

    render(<SourceTypeStep selectedSourceType="documents" onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /structured records/i }))
    fireEvent.click(screen.getByRole('button', { name: /documents/i }))

    expect(onChange).toHaveBeenNthCalledWith(1, 'records')
    expect(onChange).toHaveBeenNthCalledWith(2, 'documents')
  })

  it('marks the selected source type', () => {
    render(<SourceTypeStep selectedSourceType="records" onChange={() => undefined} />)

    expect(screen.getByRole('button', { name: /structured records/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByRole('button', { name: /documents/i })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })
})
