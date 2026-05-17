import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SourceTypeStep } from '../SourceTypeStep'

describe('SourceTypeStep', () => {
  it('calls onChange when a source choice is clicked', () => {
    const onChange = vi.fn()

    const { rerender } = render(
      <SourceTypeStep selectedSourceType="documents" onChange={onChange} />,
    )

    fireEvent.click(screen.getByRole('radio', { name: /structured records/i }))
    rerender(<SourceTypeStep selectedSourceType="records" onChange={onChange} />)
    fireEvent.click(screen.getByRole('radio', { name: /documents/i }))

    expect(onChange).toHaveBeenNthCalledWith(1, 'records')
    expect(onChange).toHaveBeenNthCalledWith(2, 'documents')
  })

  it('renders source choices as a native radio group with the selected source checked', () => {
    render(<SourceTypeStep selectedSourceType="records" onChange={() => undefined} />)

    expect(screen.getByRole('group', { name: /source type/i })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /structured records/i })).toBeChecked()
    expect(screen.getByRole('radio', { name: /documents/i })).not.toBeChecked()
  })

  it('supports keyboard selection through native radio inputs', () => {
    const onChange = vi.fn()

    render(<SourceTypeStep selectedSourceType="documents" onChange={onChange} />)

    fireEvent.keyDown(screen.getByRole('radio', { name: /structured records/i }), {
      key: ' ',
      code: 'Space',
    })
    fireEvent.click(screen.getByRole('radio', { name: /structured records/i }))

    expect(onChange).toHaveBeenCalledWith('records')
    expect(screen.getByRole('radio', { name: /structured records/i })).toHaveAttribute(
      'type',
      'radio',
    )
    expect(screen.getByRole('radio', { name: /documents/i })).toHaveAttribute(
      'name',
      'ingestion-source-type',
    )
  })
})
