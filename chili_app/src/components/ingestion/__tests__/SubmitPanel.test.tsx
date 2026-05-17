import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SubmitPanel } from '../SubmitPanel'

describe('SubmitPanel', () => {
  it('calls document and records submit actions independently', () => {
    const onSubmitDocuments = vi.fn()
    const onSubmitRecords = vi.fn()

    render(
      <SubmitPanel
        canSubmitDocuments
        canSubmitRecords
        documentPending={false}
        recordsPending={false}
        onSubmitDocuments={onSubmitDocuments}
        onSubmitRecords={onSubmitRecords}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Submit documents' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit records' }))

    expect(onSubmitDocuments).toHaveBeenCalledTimes(1)
    expect(onSubmitRecords).toHaveBeenCalledTimes(1)
  })

  it('disables each action when it cannot submit or is pending', () => {
    render(
      <SubmitPanel
        canSubmitDocuments={false}
        canSubmitRecords
        documentPending={false}
        recordsPending
        onSubmitDocuments={vi.fn()}
        onSubmitRecords={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Submit documents' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Submit records' })).toBeDisabled()
    expect(screen.getByText('Select documents')).toBeInTheDocument()
    expect(screen.getByText('Submitting records')).toBeInTheDocument()
    expect(screen.queryByText('Documents ready')).not.toBeInTheDocument()
  })

  it('shows unavailable copy when records cannot be submitted', () => {
    render(
      <SubmitPanel
        canSubmitDocuments
        canSubmitRecords={false}
        documentPending={false}
        recordsPending={false}
        onSubmitDocuments={vi.fn()}
        onSubmitRecords={vi.fn()}
      />,
    )

    expect(screen.getByText('Documents ready')).toBeInTheDocument()
    expect(screen.getByText('Parse records')).toBeInTheDocument()
    expect(screen.queryByText('Records ready')).not.toBeInTheDocument()
  })

  it('shows pending copy without changing the action labels', () => {
    render(
      <SubmitPanel
        canSubmitDocuments
        canSubmitRecords
        documentPending
        recordsPending
        onSubmitDocuments={vi.fn()}
        onSubmitRecords={vi.fn()}
      />,
    )

    const panel = screen.getByRole('region', { name: /submit ingestion/i })

    expect(within(panel).getByRole('button', { name: 'Submit documents' })).toBeDisabled()
    expect(within(panel).getByRole('button', { name: 'Submit records' })).toBeDisabled()
    expect(within(panel).getByText('Submitting documents')).toBeInTheDocument()
    expect(within(panel).getByText('Submitting records')).toBeInTheDocument()
  })
})
